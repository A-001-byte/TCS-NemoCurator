"""
pipeline/dedup.py  —  Stage 3: deduplication + Stream B boilerplate awareness
==============================================================================
Reads data/cleaned/*.json, writes surviving chunks to data/deduped/chunks.jsonl.

Original exact + fuzzy deduplication logic (SHA-256 exact matching,
MinHash/LSH via datasketch) is preserved unchanged.

Stream B adds:

  Rule 2 — Regulatory-boilerplate-aware deduplication  (B0.5-B0.7)

    Distinguishes two qualitatively different fuzzy-duplicate phenomena:

    a) CROSS-DOCUMENT BOILERPLATE — the same RBI definition clause or
       standard disclaimer appearing across MULTIPLE DIFFERENT bank policy
       PDFs. E.g., the RBI Master Direction definition of "Beneficial Owner"
       appears nearly verbatim in Central Bank of India, Nainital Bank,
       and Equitas SFB policy documents.

    b) INTRA-DOCUMENT NEAR-DUPLICATE — repeated content within the SAME
       source PDF (running headers, repeated section titles, tables with
       repeated row structures). Pure noise.

    WHY this distinction matters for BFSI specifically:
      - Cross-document boilerplate is traceable to a canonical regulatory
        source (the RBI Master Direction). Knowing WHICH bank documents
        reference it is itself useful metadata for a compliance training
        corpus.
      - Intra-doc noise should be aggressively removed; cross-doc boilerplate
        should be removed (keeping one canonical copy) but COUNTED separately
        so the pipeline knows how much of the dedup reduction was boilerplate
        versus noise.

NeMo-Curator-equivalent stage, library integration pending (Stream A).
"""
import hashlib
import json
import sys
from pathlib import Path

from datasketch import MinHash, MinHashLSH

# ---------------------------------------------------------------------------
# PATHS (match existing codebase convention)
# ---------------------------------------------------------------------------

CLEANED_DIR = Path(__file__).resolve().parent.parent / "data" / "cleaned"
DEDUPED_DIR = Path(__file__).resolve().parent.parent / "data" / "deduped"
STAGE_RECORD_PATH = DEDUPED_DIR / "_stage_record.json"
OUT_PATH = DEDUPED_DIR / "chunks.jsonl"

# ---------------------------------------------------------------------------
# TUNABLE CONSTANTS  (B1.2)
# ---------------------------------------------------------------------------

MIN_CHUNK_CHARS = 120
FUZZY_THRESHOLD = 0.8
NUM_PERM = 64
CHUNK_WORDS = 180


# ---------------------------------------------------------------------------
# HELPERS (existing logic, preserved)
# ---------------------------------------------------------------------------

def split_into_chunks(text: str):
    """Split into fixed-size word windows.

    PDF extraction frequently loses blank-line paragraph breaks (pdfplumber emits
    one line per visual line, not per paragraph), so splitting on "\\n\\n" alone
    can collapse an entire multi-page document into a single "paragraph". Fixed-size
    windows give consistent, comparably-sized chunks regardless of source formatting,
    which both dedup (MinHash needs comparable granularity) and the quality filter
    (lexical-diversity ratio is only meaningful at paragraph scale) depend on.
    """
    words = text.split()
    chunks = []
    for i in range(0, len(words), CHUNK_WORDS):
        chunk = " ".join(words[i : i + CHUNK_WORDS])
        if len(chunk) >= MIN_CHUNK_CHARS:
            chunks.append(chunk)
    return chunks


def shingles(text: str, k: int = 5):
    words = text.lower().split()
    return {" ".join(words[i : i + k]) for i in range(max(len(words) - k + 1, 1))}


def minhash_for(text: str) -> MinHash:
    mh = MinHash(num_perm=NUM_PERM)
    for sh in shingles(text):
        mh.update(sh.encode("utf-8"))
    return mh


# ---------------------------------------------------------------------------
# EXISTING EXACT DEDUP (v1, preserved unchanged)
# ---------------------------------------------------------------------------

def _exact_dedup(chunks: list) -> tuple:
    """
    Remove exact duplicates by SHA-256 hash of normalised text.
    Returns (survivors, exact_removed_count).
    """
    seen_hashes = set()
    survivors = []
    removed = 0
    for chunk in chunks:
        h = hashlib.sha256(chunk["text"].encode("utf-8")).hexdigest()
        if h in seen_hashes:
            removed += 1
        else:
            seen_hashes.add(h)
            survivors.append(chunk)
    return survivors, removed


# ---------------------------------------------------------------------------
# STREAM B: BOILERPLATE-AWARE FUZZY DEDUP  (B0.5-B0.7)
# ---------------------------------------------------------------------------

def _fuzzy_dedup_with_boilerplate_awareness(chunks: list) -> tuple:
    """
    MinHash/LSH fuzzy dedup that distinguishes:
      - cross_doc_boilerplate: near-duplicate pair from different doc_ids
      - intra_doc_near_duplicate: near-duplicate pair from the same doc_id

    Returns:
      (survivors, cross_doc_boilerplate_removed, intra_doc_near_dup_removed)

    Algorithm:
      1. Build MinHash for every chunk.
      2. For each chunk (in order), query LSH against already-kept chunks.
         If any already-kept chunk is a near-duplicate:
           - if different doc_id  -> cross_doc_boilerplate, skip
           - if same doc_id       -> intra_doc_near_duplicate, skip
         If no near-duplicate found, keep this chunk and insert into LSH.
    """
    if not chunks:
        return [], 0, 0

    lsh = MinHashLSH(threshold=FUZZY_THRESHOLD, num_perm=NUM_PERM)
    chunk_by_id = {}

    removed_cross_doc = 0
    removed_intra_doc = 0
    survivors = []

    for chunk in chunks:
        cid = chunk["chunk_id"]
        mh = minhash_for(chunk["text"])

        # Query before inserting so we don't match against self
        neighbours = lsh.query(mh)

        duplicate_of = None
        for neighbour_id in neighbours:
            if neighbour_id != cid:
                duplicate_of = neighbour_id
                break

        if duplicate_of is not None:
            # Classify the duplicate
            this_doc  = chunk["doc_id"]
            other_doc = chunk_by_id[duplicate_of]["doc_id"]
            if this_doc != other_doc:
                removed_cross_doc += 1
            else:
                removed_intra_doc += 1
        else:
            lsh.insert(cid, mh)
            chunk_by_id[cid] = chunk
            survivors.append(chunk)

    return survivors, removed_cross_doc, removed_intra_doc


# ---------------------------------------------------------------------------
# MAIN ENTRY POINT (called by pipeline/run.py)
# ---------------------------------------------------------------------------

def main():
    DEDUPED_DIR.mkdir(parents=True, exist_ok=True)
    doc_files = sorted(p for p in CLEANED_DIR.glob("*.json") if not p.name.startswith("_"))

    all_chunks = []
    for doc_path in doc_files:
        record = json.loads(doc_path.read_text(encoding="utf-8"))
        for idx, chunk_text in enumerate(split_into_chunks(record["text"])):
            all_chunks.append(
                {
                    "chunk_id": f"{record['doc_id']}__{idx}",
                    "doc_id": record["doc_id"],
                    "source_file": record["source_file"],
                    "text": chunk_text,
                }
            )

    chunks_in = len(all_chunks)

    # Stage 1: exact dedup (unchanged from v1)
    after_exact, exact_removed = _exact_dedup(all_chunks)

    # Stage 2: boilerplate-aware fuzzy dedup (Stream B)
    fuzzy_survivors, cross_doc_removed, intra_doc_removed = \
        _fuzzy_dedup_with_boilerplate_awareness(after_exact)

    with OUT_PATH.open("w", encoding="utf-8") as f:
        for chunk in fuzzy_survivors:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    total_removed = exact_removed + cross_doc_removed + intra_doc_removed

    record = {
        "stage": "dedup",
        "docs_in": chunks_in,
        "docs_out": len(fuzzy_survivors),
        "removed": total_removed,
        "reason_counts": {
            "exact_duplicate": exact_removed,
            # Stream B: replaces old undifferentiated "fuzzy_duplicate" (B0.6)
            "cross_doc_boilerplate": cross_doc_removed,
            "intra_doc_near_duplicate": intra_doc_removed,
        },
    }
    STAGE_RECORD_PATH.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, indent=2))

    if len(fuzzy_survivors) == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
