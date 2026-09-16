"""Stage 4: heuristic quality filtering over deduped chunks.
Reads data/deduped/chunks.jsonl, writes surviving chunks to data/filtered/chunks.jsonl.

This is an equivalent-logic heuristic filter, not the NeMo Curator DeBERTa quality
classifier (nvidia/quality-classifier-deberta). Labelled as such in the dashboard/README.
"""
import json
import re
import sys
from pathlib import Path

DEDUPED_DIR = Path(__file__).resolve().parent.parent / "data" / "deduped"
FILTERED_DIR = Path(__file__).resolve().parent.parent / "data" / "filtered"
STAGE_RECORD_PATH = FILTERED_DIR / "_stage_record.json"
IN_PATH = DEDUPED_DIR / "chunks.jsonl"
OUT_PATH = FILTERED_DIR / "chunks.jsonl"

MIN_WORDS = 15
MAX_SYMBOL_RATIO = 0.3
MIN_ALPHA_RATIO = 0.5
WORD_RE = re.compile(r"\w+")
ALPHA_RE = re.compile(r"[A-Za-z]")


def quality_reason(text: str):
    words = WORD_RE.findall(text)
    if len(words) < MIN_WORDS:
        return "too_few_words"

    alpha_chars = len(ALPHA_RE.findall(text))
    if alpha_chars / max(len(text), 1) < MIN_ALPHA_RATIO:
        return "low_alpha_ratio"

    symbol_chars = sum(1 for c in text if not c.isalnum() and not c.isspace())
    if symbol_chars / max(len(text), 1) > MAX_SYMBOL_RATIO:
        return "high_symbol_ratio"

    unique_words = set(w.lower() for w in words)
    if len(unique_words) / len(words) < 0.3:
        return "low_lexical_diversity"

    return None


def main():
    FILTERED_DIR.mkdir(parents=True, exist_ok=True)
    if not IN_PATH.exists():
        print(json.dumps({"stage": "quality_filter", "error": "no input chunks"}))
        sys.exit(1)

    chunks_in = 0
    survivors = []
    reason_counts = {}

    with IN_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            chunk = json.loads(line)
            chunks_in += 1
            reason = quality_reason(chunk["text"])
            if reason:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
                continue
            survivors.append(chunk)

    with OUT_PATH.open("w", encoding="utf-8") as f:
        for chunk in survivors:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    record = {
        "stage": "quality_filter",
        "docs_in": chunks_in,
        "docs_out": len(survivors),
        "removed": chunks_in - len(survivors),
        "reason_counts": reason_counts,
    }
    STAGE_RECORD_PATH.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, indent=2))

    if len(survivors) == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
