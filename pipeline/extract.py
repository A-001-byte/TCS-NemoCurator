"""Stage 1: PDF text extraction. Real RBI/bank PDFs in data/raw -> plain text in data/extracted."""
import json
import sys
from pathlib import Path

import pdfplumber

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
EXTRACTED_DIR = Path(__file__).resolve().parent.parent / "data" / "extracted"
STAGE_RECORD_PATH = EXTRACTED_DIR / "_stage_record.json"


def extract_pdf_text(pdf_path: Path) -> str:
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text)
    return "\n".join(pages)


def main():
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(RAW_DIR.glob("*.pdf"))
    docs_in = len(pdfs)
    docs_out = 0
    failures = []

    for pdf_path in pdfs:
        out_path = EXTRACTED_DIR / (pdf_path.stem + ".txt")
        try:
            text = extract_pdf_text(pdf_path)
        except Exception as exc:
            failures.append({"file": pdf_path.name, "error": str(exc)})
            continue
        if not text.strip():
            failures.append({"file": pdf_path.name, "error": "empty extraction"})
            continue
        out_path.write_text(text, encoding="utf-8")
        docs_out += 1

    record = {
        "stage": "extract",
        "docs_in": docs_in,
        "docs_out": docs_out,
        "removed": docs_in - docs_out,
        "reason_counts": {"extraction_failed": len(failures)},
        "failures": failures,
    }
    STAGE_RECORD_PATH.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, indent=2))

    if docs_out == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
