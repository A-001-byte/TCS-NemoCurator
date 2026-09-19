"""Stage 2b: Page-Splice Healing -- raise corpus purity without dropping content.

PDF page furniture (running headers, footers, letterheads, classification stamps) is
extracted inline, so it lands in the MIDDLE of legal sentences at every page break:

    ...interest or who exercises control through other means.
    <Hindi letterhead line>                                          <- furniture
    KYC - AML Cell, Planning, Development & Operations Department,   <- furniture
    M.G. Road, Fort, Mumbai-400001.                                  <- furniture
    (next page continues the sentence)

Keep-or-drop curation (heuristic filters, dedup) cannot remove this without discarding
the real content around it. This stage deletes ONLY the furniture lines, so the text on
either side of each page break joins back up. No document or content line is dropped.

Detection signal is periodicity, not frequency: furniture recurs about once per page, so
its occurrences are many, spread across the whole document, and evenly spaced at
page-length gaps. Legitimately repeated content -- a defined term, a table row reused in
several report formats -- recurs irregularly or at section-length gaps. Frequency alone
cannot tell those apart; spacing can.

Second pass, corpus-consensus OCR repair: kerning splits ("f inancial", "Mandat ory") are
merged when the joined word occurs intact elsewhere in the corpus and a fragment does
not. The corpus is its own dictionary -- no wordlist, no model.

Standalone for now (reads data/cleaned, writes data/healed): run.py is unchanged until
Stream B agrees, because healing shifts every downstream count.
Run: python -m pipeline.heal
"""
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

from datasketch import MinHashLSH

from pipeline import dedup
from pipeline.pii import PATTERNS

ROOT = Path(__file__).resolve().parent.parent
CLEANED_DIR = ROOT / "data" / "cleaned"
HEALED_DIR = ROOT / "data" / "healed"
STAGE_RECORD_PATH = HEALED_DIR / "_stage_record.json"
REPORT_PATH = HEALED_DIR / "heal_report.json"

# Tuned on the real corpus. True furniture: >=15 occurrences, span >=0.89, gap CV <=0.28,
# mean gap 31-43 lines. Nearest look-alike content (FIU schema rows reused per report
# format) has mean gap >=1273 lines, so MAX_MEAN_GAP separates them with a wide margin.
MIN_REPEATS = 8
MIN_SPAN = 0.5
MAX_GAP_CV = 0.5
MIN_MEAN_GAP = 10
MAX_MEAN_GAP = 150  # ponytail: lines-per-page proxy; raise for sources with >150 lines/page
MIN_LINE_CHARS = 8

MIN_MERGED_FREQ = 3
MAX_FRAGMENT_FREQ = 2

DEVANAGARI_RE = re.compile("[ऀ-ॿ]")
PAGE_MARKER_RE = re.compile(r"\bP ?age\s*(\|\s*)?\d+(\s+of\s+\d+)?", re.IGNORECASE)
WORD_RE = re.compile(r"[A-Za-z]+")
PINCODE_RE = dict(PATTERNS)["PINCODE"]


def _signature(line: str) -> str:
    """Page numbers and dates vary per page; everything else about furniture does not."""
    return re.sub(r"\d+", "#", " ".join(line.split())).lower()


def find_furniture(lines: list) -> dict:
    """Signatures of lines that recur about once per page across the whole document."""
    positions = {}
    for i, line in enumerate(lines):
        sig = _signature(line)
        if len(sig.replace(" ", "")) >= MIN_LINE_CHARS:
            positions.setdefault(sig, []).append(i)

    furniture = {}
    for sig, idx in positions.items():
        if len(idx) < MIN_REPEATS:
            continue
        gaps = [b - a for a, b in zip(idx, idx[1:])]
        mean_gap = statistics.mean(gaps)
        cv = statistics.pstdev(gaps) / mean_gap
        span = (idx[-1] - idx[0]) / len(lines)
        if span >= MIN_SPAN and cv <= MAX_GAP_CV and MIN_MEAN_GAP <= mean_gap <= MAX_MEAN_GAP:
            furniture[sig] = {
                "occurrences": len(idx),
                "gap_cv": round(cv, 3),
                "mean_gap_lines": round(mean_gap, 1),
                "span": round(span, 3),
            }
    return furniture


def remove_furniture(text: str) -> tuple:
    lines = text.split("\n")
    furniture = find_furniture(lines)
    kept = [line for line in lines if _signature(line) not in furniture]
    return "\n".join(kept), furniture, len(lines) - len(kept)


def repair_ocr_splits(text: str, vocab: Counter) -> tuple:
    """Merge kerning splits ("f inancial") that the rest of the corpus spells intact."""
    tokens = list(WORD_RE.finditer(text))
    pieces, repairs, last, i = [], [], 0, 0
    while i < len(tokens) - 1:
        a, b = tokens[i], tokens[i + 1]
        merged = a.group() + b.group()
        if (
            text[a.end() : b.start()] == " "
            and vocab[merged.lower()] >= MIN_MERGED_FREQ
            and min(vocab[a.group().lower()], vocab[b.group().lower()]) <= MAX_FRAGMENT_FREQ
        ):
            pieces += [text[last : a.start()], merged]
            repairs.append(f"{a.group()} {b.group()} -> {merged}")
            last, i = b.end(), i + 2
        else:
            i += 1
    pieces.append(text[last:])
    return "".join(pieces), repairs


def _duplicate_chunks(chunks: list) -> int:
    """Exact + fuzzy duplicates, same rule and thresholds as the dedup stage."""
    seen, dupes = set(), 0
    lsh = MinHashLSH(threshold=dedup.FUZZY_THRESHOLD, num_perm=dedup.NUM_PERM)
    for i, chunk in enumerate(chunks):
        if chunk in seen:
            dupes += 1
            continue
        seen.add(chunk)
        mh = dedup.minhash_for(chunk)
        if lsh.query(mh):
            dupes += 1
            continue
        lsh.insert(str(i), mh)
    return dupes


def purity_metrics(docs: dict) -> dict:
    """Measured on pre-quality-filter chunks cut by the real dedup-stage chunker."""
    chunks = [c for text in docs.values() for c in dedup.split_into_chunks(text)]
    return {
        "chunks": len(chunks),
        "chunks_with_devanagari": sum(1 for c in chunks if DEVANAGARI_RE.search(c)),
        "chunks_with_page_marker": sum(1 for c in chunks if PAGE_MARKER_RE.search(c)),
        "pincode_spans": sum(len(PINCODE_RE.findall(c)) for c in chunks),
        "duplicate_chunks": _duplicate_chunks(chunks),
        "total_chars": sum(len(t) for t in docs.values()),
    }


def main():
    HEALED_DIR.mkdir(parents=True, exist_ok=True)
    records = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(CLEANED_DIR.glob("*.json"))
        if not p.name.startswith("_")
    ]
    if not records:
        print(json.dumps({"stage": "heal", "error": "no cleaned documents"}))
        sys.exit(1)

    healed, per_doc = {}, {}
    for rec in records:
        text, furniture, removed = remove_furniture(rec["text"])
        healed[rec["doc_id"]] = text
        per_doc[rec["doc_id"]] = {"furniture_lines_removed": removed, "furniture": furniture}

    vocab = Counter(w.lower() for t in healed.values() for w in WORD_RE.findall(t))
    for rec in records:
        text, repairs = repair_ocr_splits(healed[rec["doc_id"]], vocab)
        healed[rec["doc_id"]] = text
        per_doc[rec["doc_id"]]["ocr_repairs"] = repairs
        out = {**rec, "text": text, "char_count": len(text)}
        (HEALED_DIR / f"{rec['doc_id']}.json").write_text(
            json.dumps(out, ensure_ascii=False), encoding="utf-8"
        )

    before = purity_metrics({r["doc_id"]: r["text"] for r in records})
    after = purity_metrics(healed)
    record = {
        "stage": "heal",
        "docs_in": len(records),
        "docs_out": len(records),
        "removed": 0,
        "reason_counts": {
            "furniture_lines_removed": sum(d["furniture_lines_removed"] for d in per_doc.values()),
            "furniture_signatures": sum(len(d["furniture"]) for d in per_doc.values()),
            "ocr_splits_repaired": sum(len(d["ocr_repairs"]) for d in per_doc.values()),
        },
        "before": before,
        "after": after,
    }
    STAGE_RECORD_PATH.write_text(json.dumps(record, indent=2), encoding="utf-8")
    REPORT_PATH.write_text(
        json.dumps({"before": before, "after": after, "documents": per_doc}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
