"""Stage 3: deduplication (exact, then fuzzy MinHash) over paragraph-level chunks.
Reads data/cleaned/*.json, writes surviving chunks to data/deduped/chunks.jsonl.
Regulatory boilerplate (definitions, disclaimers, standard clauses) repeats across
these documents, so this stage is expected to visibly remove a nontrivial fraction.
"""
import hashlib
import json
import sys
from pathlib import Path

from datasketch import MinHash, MinHashLSH

CLEANED_DIR = Path(__file__).resolve().parent.parent / "data" / "cleaned"
DEDUPED_DIR = Path(__file__).resolve().parent.parent / "data" / "deduped"
STAGE_RECORD_PATH = DEDUPED_DIR / "_stage_record.json"
OUT_PATH = DEDUPED_DIR / "chunks.jsonl"

MIN_CHUNK_CHARS = 120
FUZZY_THRESHOLD = 0.8
NUM_PERM = 64
CHUNK_WORDS = 180


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

    # exact dedup via sha256
    seen_hashes = set()
    exact_survivors = []
    exact_removed = 0
    for chunk in all_chunks:
        h = hashlib.sha256(chunk["text"].encode("utf-8")).hexdigest()
        if h in seen_hashes:
            exact_removed += 1
            continue
        seen_hashes.add(h)
        exact_survivors.append(chunk)

    # fuzzy dedup via MinHash LSH
    lsh = MinHashLSH(threshold=FUZZY_THRESHOLD, num_perm=NUM_PERM)
    fuzzy_survivors = []
    fuzzy_removed = 0
    for chunk in exact_survivors:
        mh = minhash_for(chunk["text"])
        result = lsh.query(mh)
        if result:
            fuzzy_removed += 1
            continue
        lsh.insert(chunk["chunk_id"], mh)
        fuzzy_survivors.append(chunk)

    with OUT_PATH.open("w", encoding="utf-8") as f:
        for chunk in fuzzy_survivors:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    record = {
        "stage": "dedup",
        "docs_in": chunks_in,
        "docs_out": len(fuzzy_survivors),
        "removed": exact_removed + fuzzy_removed,
        "reason_counts": {"exact_duplicate": exact_removed, "fuzzy_duplicate": fuzzy_removed},
    }
    STAGE_RECORD_PATH.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, indent=2))

    if len(fuzzy_survivors) == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
