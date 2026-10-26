"""Stage 1: PDF text extraction. Real RBI/bank PDFs in data/raw -> plain text in data/extracted."""

import json
import sys
from pathlib import Path

import pdfplumber

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
EXTRACTED_DIR = Path(__file__).resolve().parent.parent / "data" / "extracted"
STAGE_RECORD_PATH = EXTRACTED_DIR / "_stage_record.json"
PAGES_SUFFIX = ".pages.json"  # next to each document's .txt: {"pages": [text of page 1, text of page 2, ...]}


def list_pdfs(folder: Path) -> list:
    """The input PDFs in `folder`, sorted: regular files whose extension is .pdf in any letter case.
    (Path.glob("*.pdf") is case-sensitive on Linux but not on Windows, and also matches folders.)"""
    return sorted(p for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() == ".pdf")


def extract_pdf_pages(pdf_path: Path) -> list:
    """The text of each page, in order (an empty string for a page with no text layer)."""
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return pages


def extract_pdf_text(pdf_path: Path) -> str:
    return "\n".join(extract_pdf_pages(pdf_path))


def main():
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = list_pdfs(RAW_DIR)
    docs_in = len(pdfs)
    docs_out = 0
    failures = []

    for pdf_path in pdfs:
        out_path = EXTRACTED_DIR / (pdf_path.stem + ".txt")
        try:
            pages = extract_pdf_pages(pdf_path)
        except Exception as exc:
            failures.append({"file": pdf_path.name, "error": str(exc)})
            continue
        text = "\n".join(pages)
        if not text.strip():
            failures.append({"file": pdf_path.name, "error": "empty extraction"})
            continue
        out_path.write_text(text, encoding="utf-8")
        # Kept so a chunk can be traced back to its page later (pipeline/pages.py); the clean stage reads only *.txt.
        (EXTRACTED_DIR / (pdf_path.stem + PAGES_SUFFIX)).write_text(
            json.dumps({"pages": pages}, ensure_ascii=False), encoding="utf-8", newline="\n"
        )
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
