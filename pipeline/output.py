"""Stage 6: fine-tuning-ready JSONL output.
Reads data/redacted/chunks.jsonl, writes data/output/curated.jsonl.
Each line is a valid JSON object with a `text` field, ready for SFT-style fine-tuning.
"""
import json
import sys
from pathlib import Path

REDACTED_DIR = Path(__file__).resolve().parent.parent / "data" / "redacted"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "output"
STAGE_RECORD_PATH = OUTPUT_DIR / "_stage_record.json"
IN_PATH = REDACTED_DIR / "chunks.jsonl"
OUT_PATH = OUTPUT_DIR / "curated.jsonl"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not IN_PATH.exists():
        print(json.dumps({"stage": "output", "error": "no redacted chunks"}))
        sys.exit(1)

    docs_in = 0
    docs_out = 0
    total_chars = 0

    with IN_PATH.open(encoding="utf-8") as f_in, OUT_PATH.open("w", encoding="utf-8") as f_out:
        for line in f_in:
            line = line.strip()
            if not line:
                continue
            chunk = json.loads(line)
            docs_in += 1
            record = {
                "text": chunk["text"],
                "metadata": {
                    "chunk_id": chunk["chunk_id"],
                    "doc_id": chunk["doc_id"],
                    "source_file": chunk["source_file"],
                    "pii_redacted": chunk.get("pii_redacted", False),
                },
            }
            f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
            docs_out += 1
            total_chars += len(chunk["text"])

    record = {
        "stage": "output",
        "docs_in": docs_in,
        "docs_out": docs_out,
        "removed": docs_in - docs_out,
        "reason_counts": {},
        "total_chars": total_chars,
        "output_path": str(OUT_PATH),
    }
    STAGE_RECORD_PATH.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, indent=2))

    if docs_out == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
