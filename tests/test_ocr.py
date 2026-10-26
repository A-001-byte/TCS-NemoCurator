"""Optional OCR for scanned PDFs. Tesseract itself is stubbed: these tests check when OCR is used, not how well it reads."""

import json
import shutil
import sys
import types
from pathlib import Path

import pypdfium2
import pytest

from pipeline import api, cli, extract, run

SCAN = "bank_of_baroda_aml_questionnaire.pdf"  # the corpus's one scanned PDF: no text layer
TEXT_PDF = "fiu_india_brochure.pdf"


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """extract pointed at temporary folders; returns (raw folder, extracted folder, a function that runs the stage)."""
    raw, extracted = tmp_path / "raw", tmp_path / "extracted"
    raw.mkdir()
    monkeypatch.setattr(extract, "RAW_DIR", raw)
    monkeypatch.setattr(extract, "EXTRACTED_DIR", extracted)
    monkeypatch.setattr(extract, "STAGE_RECORD_PATH", extracted / "_stage_record.json")

    def stage():
        try:
            extract.main()
        except SystemExit:
            pass
        return json.loads((extracted / "_stage_record.json").read_text(encoding="utf-8"))

    return raw, extracted, stage


def put(raw: Path, name: str) -> None:
    shutil.copy(run.ROOT / "data" / "raw" / name, raw / name)


def page_count(raw: Path, name: str) -> int:
    """Pages according to pdfium, which (unlike pdfplumber) opens the corpus's scanned PDF."""
    document = pypdfium2.PdfDocument(str(raw / name))
    try:
        return len(document)
    finally:
        document.close()


def test_the_scanned_pdf_really_has_pages_that_pdfplumber_cannot_see(workspace):
    # The reason OCR draws pages with pdfium: this file has 6 pages, and pdfplumber reports none.
    import pdfplumber

    raw, _, _ = workspace
    put(raw, SCAN)
    assert page_count(raw, SCAN) > 0
    with pdfplumber.open(raw / SCAN) as pdf:
        assert len(pdf.pages) == 0


def test_a_scanned_pdf_fails_cleanly_when_ocr_is_off(workspace):
    raw, _, stage = workspace
    put(raw, SCAN)
    record = stage()
    assert record["docs_out"] == 0 and record["failures"][0]["error"] == "empty extraction"
    assert record["ocr"] is False and record["ocr_pages"] == 0


def test_a_scanned_pdf_is_read_when_ocr_is_on(workspace, monkeypatch):
    raw, extracted, stage = workspace
    put(raw, SCAN)
    numbers = iter(range(1, 1000))
    monkeypatch.setattr(extract, "OCR_ENABLED", True)
    monkeypatch.setattr(extract, "ocr_page_text", lambda page: f"Scanned page {next(numbers)} text read by OCR.")
    record = stage()
    total = page_count(raw, SCAN)
    assert record["docs_out"] == 1 and record["failures"] == []
    assert record["ocr"] is True and record["ocr_pages"] == total
    kept = json.loads((extracted / (Path(SCAN).stem + extract.PAGES_SUFFIX)).read_text(encoding="utf-8"))["pages"]
    assert kept == [f"Scanned page {n} text read by OCR." for n in range(1, total + 1)]


def test_ocr_is_used_only_for_pages_with_no_text_layer(workspace, monkeypatch):
    raw, _, stage = workspace
    put(raw, TEXT_PDF)

    def must_not_run(page):
        raise AssertionError("OCR was called on a page that has a text layer")

    monkeypatch.setattr(extract, "OCR_ENABLED", True)
    monkeypatch.setattr(extract, "ocr_page_text", must_not_run)
    record = stage()
    assert record["docs_out"] == 1 and record["ocr_pages"] == 0


def test_a_page_that_ocr_cannot_read_is_not_counted(workspace, monkeypatch):
    raw, _, stage = workspace
    put(raw, SCAN)
    monkeypatch.setattr(extract, "OCR_ENABLED", True)
    monkeypatch.setattr(extract, "ocr_page_text", lambda page: "   ")
    record = stage()
    assert record["docs_out"] == 0 and record["ocr_pages"] == 0


def test_ocr_reports_a_missing_python_package(monkeypatch):
    monkeypatch.setitem(sys.modules, "pytesseract", None)  # makes `import pytesseract` raise ImportError
    assert "pytesseract package" in extract.ocr_unavailable_reason()


def test_ocr_reports_a_missing_tesseract_program(monkeypatch):
    monkeypatch.setitem(sys.modules, "pytesseract", types.ModuleType("pytesseract"))
    monkeypatch.setattr(extract.shutil, "which", lambda name: None)
    assert "Tesseract program" in extract.ocr_unavailable_reason()


def test_ocr_is_available_when_both_pieces_are_present(monkeypatch):
    monkeypatch.setitem(sys.modules, "pytesseract", types.ModuleType("pytesseract"))
    monkeypatch.setattr(extract.shutil, "which", lambda name: "/usr/bin/tesseract")
    assert extract.ocr_unavailable_reason() is None


def test_curate_refuses_ocr_before_running_when_it_is_unavailable(tmp_path, monkeypatch):
    inputs = tmp_path / "in"
    inputs.mkdir()
    shutil.copy(run.ROOT / "data" / "raw" / TEXT_PDF, inputs / TEXT_PDF)
    monkeypatch.setattr(extract, "ocr_unavailable_reason", lambda: "OCR needs the Tesseract program on the PATH.")
    with pytest.raises(RuntimeError, match="Tesseract program"):
        api.curate(inputs, tmp_path / "out", ocr=True)
    assert not (tmp_path / "out").exists()


def test_the_ocr_setting_is_scoped_to_one_run(tmp_path, monkeypatch):
    inputs = tmp_path / "in"
    inputs.mkdir()
    shutil.copy(run.ROOT / "data" / "raw" / TEXT_PDF, inputs / TEXT_PDF)
    monkeypatch.setattr(extract, "ocr_unavailable_reason", lambda: None)
    seen = []
    original = extract.read_pdf

    def spy(pdf_path, ocr=False):
        seen.append(ocr)
        return original(pdf_path, ocr)

    monkeypatch.setattr(extract, "read_pdf", spy)
    api.curate(inputs, tmp_path / "out", device="cpu", ocr=True)
    assert seen == [True] and extract.OCR_ENABLED is False


def test_the_ocr_flag_reaches_curate(monkeypatch):
    seen = {}

    def fake_curate(pdf_dir, output, device, **options):
        seen.update(options)
        summary = {"stages": [], "final_output_chunks": 1, "pii_entities_redacted": 0}
        return api.CurateResult(summary, Path("out/curated.jsonl"), Path("out/pipeline_summary.json"), "cpu", "")

    monkeypatch.setattr(api, "curate", fake_curate)
    assert cli.main(["run", "in", "-o", "out", "--ocr"]) == 0
    assert seen["ocr"] is True
    cli.main(["run", "in", "-o", "out"])
    assert seen["ocr"] is False
