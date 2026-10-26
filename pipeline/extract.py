"""Stage 1: PDF text extraction. Real RBI/bank PDFs in data/raw -> plain text in data/extracted.

Pages with no text layer (scans) give no text and, by default, make the document fail extraction cleanly. With OCR on
(`bfsi-curate run --ocr`, `curate(..., ocr=True)`), such pages are drawn to an image and read with Tesseract instead.
OCR is off by default: it needs the Tesseract program, it is slow, and its text is noisier than a real text layer.
"""

import json
import shutil
import sys
from pathlib import Path
from typing import Optional

import pdfplumber

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
EXTRACTED_DIR = Path(__file__).resolve().parent.parent / "data" / "extracted"
STAGE_RECORD_PATH = EXTRACTED_DIR / "_stage_record.json"
PAGES_SUFFIX = ".pages.json"  # next to each document's .txt: {"pages": [text of page 1, text of page 2, ...]}

OCR_ENABLED = False  # set for one run by pipeline.api (curate(..., ocr=True)); needs pytesseract and Tesseract
OCR_RESOLUTION = 300  # dots per inch a page is drawn at before it is read; lower is faster and less accurate
OCR_INSTALL_HINT = "pip install pytesseract, and install the Tesseract program (Ubuntu: sudo apt install tesseract-ocr)"


def list_pdfs(folder: Path) -> list:
    """The input PDFs in `folder`, sorted: regular files whose extension is .pdf in any letter case.
    (Path.glob("*.pdf") is case-sensitive on Linux but not on Windows, and also matches folders.)"""
    return sorted(p for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() == ".pdf")


def ocr_unavailable_reason() -> Optional[str]:
    """Why OCR cannot run on this machine, as one sentence, or None when it can."""
    try:
        import pytesseract  # noqa: F401  (only checking that it is installed)
    except ImportError:
        return f"OCR needs the pytesseract package: {OCR_INSTALL_HINT}."
    if shutil.which("tesseract") is None:
        return f"OCR needs the Tesseract program on the PATH: {OCR_INSTALL_HINT}."
    return None


def ocr_page_text(page) -> str:
    """The text Tesseract reads from one pypdfium2 page, drawn at OCR_RESOLUTION."""
    import pytesseract

    return pytesseract.image_to_string(page.render(scale=OCR_RESOLUTION / 72).to_pil())


def _read_empty_pages_with_ocr(pdf_path: Path, texts: list) -> tuple:
    """`texts` with every page that has no text read by OCR, and how many pages that gave text.

    pypdfium2 draws the pages rather than pdfplumber: some scanned PDFs (the corpus has one) are not parsed by
    pdfplumber at all and report no pages, but pdfium opens them."""
    import pypdfium2

    document = pypdfium2.PdfDocument(str(pdf_path))
    try:
        texts = list(texts) + [""] * (len(document) - len(texts))
        read = 0
        for i in range(len(document)):
            if not texts[i].strip():
                texts[i] = ocr_page_text(document[i])
                read += 1 if texts[i].strip() else 0
        return texts, read
    finally:
        document.close()


def read_pdf(pdf_path: Path, ocr: bool = False) -> tuple:
    """(the text of each page, how many pages were read by OCR). A page with no text layer is OCR'd only when `ocr`."""
    with pdfplumber.open(pdf_path) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    if ocr and (not pages or any(not text.strip() for text in pages)):
        return _read_empty_pages_with_ocr(pdf_path, pages)
    return pages, 0


def extract_pdf_pages(pdf_path: Path) -> list:
    """The text of each page, in order (an empty string for a page with no text layer)."""
    return read_pdf(pdf_path)[0]


def extract_pdf_text(pdf_path: Path) -> str:
    return "\n".join(extract_pdf_pages(pdf_path))


def main():
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = list_pdfs(RAW_DIR)
    docs_in = len(pdfs)
    docs_out = 0
    ocr_pages_total = 0
    failures = []

    for pdf_path in pdfs:
        out_path = EXTRACTED_DIR / (pdf_path.stem + ".txt")
        try:
            pages, ocr_pages = read_pdf(pdf_path, OCR_ENABLED)
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
        ocr_pages_total += ocr_pages
        docs_out += 1

    record = {
        "stage": "extract",
        "docs_in": docs_in,
        "docs_out": docs_out,
        "removed": docs_in - docs_out,
        "reason_counts": {"extraction_failed": len(failures)},
        "failures": failures,
        "ocr": OCR_ENABLED,
        "ocr_pages": ocr_pages_total,
    }
    STAGE_RECORD_PATH.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, indent=2))

    if docs_out == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
