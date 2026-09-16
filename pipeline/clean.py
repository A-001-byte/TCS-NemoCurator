"""Stage 2: text cleaning/normalization + language ID.
Reads data/extracted/*.txt, writes cleaned docs as JSON records to data/cleaned/*.json.
"""
import json
import re
import sys
from pathlib import Path

from langdetect import DetectorFactory, LangDetectException, detect

DetectorFactory.seed = 0

EXTRACTED_DIR = Path(__file__).resolve().parent.parent / "data" / "extracted"
CLEANED_DIR = Path(__file__).resolve().parent.parent / "data" / "cleaned"
STAGE_RECORD_PATH = CLEANED_DIR / "_stage_record.json"

MIN_CHARS = 200
WHITESPACE_RE = re.compile(r"[ \t]+")
BLANK_LINES_RE = re.compile(r"\n{3,}")
PAGE_NUM_RE = re.compile(r"^\s*\d{1,4}\s*$")
CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def normalize_text(raw: str) -> str:
    text = CONTROL_CHARS_RE.sub("", raw)
    lines = [ln for ln in text.split("\n") if not PAGE_NUM_RE.match(ln)]
    text = "\n".join(lines)
    text = WHITESPACE_RE.sub(" ", text)
    text = BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


def detect_language(text: str) -> str:
    sample = text[:3000]
    try:
        return detect(sample)
    except LangDetectException:
        return "unknown"


def main():
    CLEANED_DIR.mkdir(parents=True, exist_ok=True)
    txt_files = sorted(EXTRACTED_DIR.glob("*.txt"))
    docs_in = len(txt_files)
    docs_out = 0
    reason_counts = {"too_short": 0, "non_english": 0}

    for txt_path in txt_files:
        raw = txt_path.read_text(encoding="utf-8")
        cleaned = normalize_text(raw)
        lang = detect_language(cleaned)

        if len(cleaned) < MIN_CHARS:
            reason_counts["too_short"] += 1
            continue
        if lang != "en":
            reason_counts["non_english"] += 1
            continue

        record = {
            "doc_id": txt_path.stem,
            "source_file": txt_path.stem + ".pdf",
            "text": cleaned,
            "lang": lang,
            "char_count": len(cleaned),
        }
        out_path = CLEANED_DIR / (txt_path.stem + ".json")
        out_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        docs_out += 1

    record = {
        "stage": "clean_langid",
        "docs_in": docs_in,
        "docs_out": docs_out,
        "removed": docs_in - docs_out,
        "reason_counts": reason_counts,
    }
    STAGE_RECORD_PATH.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, indent=2))

    if docs_out == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
