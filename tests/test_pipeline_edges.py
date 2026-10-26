"""Edge cases at the pipeline's boundaries: what counts as an input, a busy pipeline, a failing name model."""
import json
import logging
import shutil
import sys
import types
from pathlib import Path

import pytest

from pipeline import api, extract, pii

ROOT = Path(__file__).resolve().parent.parent
SMALL_PDF = ROOT / "data" / "raw" / "fiu_india_brochure.pdf"


# --- what counts as an input PDF -------------------------------------------------------------------

def test_list_pdfs_takes_regular_files_with_a_pdf_extension_in_any_case(tmp_path):
    for name in ("a.pdf", "B.PDF", "c.Pdf", "notes.txt", "d.pdf.bak", "pdf"):
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "folder.pdf").mkdir()
    assert sorted(p.name for p in extract.list_pdfs(tmp_path)) == ["B.PDF", "a.pdf", "c.Pdf"]


def test_a_folder_named_like_a_pdf_and_a_fake_pdf_are_handled_not_fatal(tmp_path):
    inputs = tmp_path / "in"
    inputs.mkdir()
    shutil.copy(SMALL_PDF, inputs / "REAL.PDF")
    (inputs / "fake.pdf").write_text("this is not a pdf")
    (inputs / "folder.pdf").mkdir()

    result = api.curate(inputs, tmp_path / "out", device="cpu")
    extract_stage = result.summary["stages"][0]
    assert (extract_stage["docs_in"], extract_stage["docs_out"]) == (2, 1), "the folder is not an input; the fake PDF is a counted failure"
    assert result.summary["final_output_chunks"] > 0
    assert "name_detection_error" in result.summary, "the summary must carry the reason when names are off"


def test_when_no_pdf_can_be_read_the_error_says_why_in_its_first_line(tmp_path):
    (tmp_path / "empty.pdf").write_bytes(b"")
    with pytest.raises(RuntimeError) as error:
        api.curate(tmp_path, tmp_path / "out", device="cpu")
    first, _, log = str(error.value).partition("\n")
    assert "extract stage" in first and "no PDF yielded any text" in first
    assert "Pipeline stopped: stage 'extract' failed" in log


@pytest.mark.parametrize("log,expected", [
    ("noise\nPipeline stopped: stage 'extract' failed (exit 1)", "extract stage: no PDF yielded any text"),
    ("Pipeline stopped: stage 'dedup' failed (exit 3)", "stopped at the dedup stage."),
    ("nothing recognisable", "The pipeline stopped before finishing."),
])
def test_stop_reason_names_the_stage_that_failed(log, expected):
    assert expected in api.stop_reason(log)


# --- one run at a time -------------------------------------------------------------------------------

def test_a_caller_that_will_not_wait_is_told_the_pipeline_is_busy():
    assert api.RUN_LOCK.acquire(blocking=False)
    try:
        with pytest.raises(api.PipelineBusy):
            api.run_isolated([("a.pdf", b"%PDF-1.4")], wait=False)
    finally:
        api.RUN_LOCK.release()
    assert api.RUN_LOCK.acquire(blocking=False), "the lock must be free again after a refused call"
    api.RUN_LOCK.release()


# --- name detection must fail loudly --------------------------------------------------------------------

@pytest.fixture
def fake_spacy(monkeypatch):
    """Replace spaCy and reset the module state, so each test sets how the model loads."""
    module = types.ModuleType("spacy")
    monkeypatch.setitem(sys.modules, "spacy", module)
    for name, value in (("_NLP", None), ("_SPACY_AVAILABLE", False), ("_SPACY_ERROR", None)):
        monkeypatch.setattr(pii, name, value)
    return module


def test_a_model_that_cannot_load_turns_names_off_with_the_reason_and_a_warning(fake_spacy, caplog):
    def refuse(*args, **kwargs):
        raise OSError("[E050] Can't find model 'en_core_web_sm'")

    fake_spacy.load = refuse
    with caplog.at_level(logging.WARNING, logger="pipeline.pii"):
        pii._load_spacy()
    assert pii._SPACY_AVAILABLE is False and pii._NLP is None
    assert "E050" in pii._SPACY_ERROR and pii._SPACY_ERROR.startswith("OSError")
    assert any("Person-name detection is OFF" in record.getMessage() for record in caplog.records)


def test_a_model_that_loads_clears_an_earlier_error(fake_spacy, monkeypatch):
    monkeypatch.setattr(pii, "_SPACY_ERROR", "OSError: old failure")
    fake_spacy.load = lambda *args, **kwargs: object()
    pii._load_spacy()
    assert pii._SPACY_AVAILABLE is True and pii._SPACY_ERROR is None


def test_the_overflow_fallback_loads_the_model_without_its_saved_tokenizer(fake_spacy):
    calls = []

    def load(name, **kwargs):
        calls.append(kwargs)
        if "exclude" not in kwargs:
            raise OverflowError("cannot deserialize the tokenizer")
        return object()

    fake_spacy.load = load
    pii._load_spacy()
    assert pii._SPACY_AVAILABLE is True and calls[1]["exclude"] == ["tokenizer"]


def test_the_stage_record_says_names_are_off_and_why(fake_spacy, tmp_path, monkeypatch):
    redacted = tmp_path / "data" / "redacted"
    redacted.mkdir(parents=True)
    filtered = tmp_path / "data" / "filtered"
    filtered.mkdir()
    chunk = {"chunk_id": "d__0", "doc_id": "d", "source_file": "d.pdf",
             "text": "Write to someone@bank.example.in about the reporting entity policy."}
    (filtered / "chunks.jsonl").write_text(json.dumps(chunk) + "\n", encoding="utf-8")
    for name, value in (
        ("REDACTED_DIR", redacted), ("IN_PATH", filtered / "chunks.jsonl"), ("OUT_PATH", redacted / "chunks.jsonl"),
        ("STAGE_RECORD_PATH", redacted / "_stage_record.json"), ("EXAMPLES_PATH", redacted / "pii_examples.json"),
        ("VALIDATION_REPORT_PATH", redacted / "validation_report.json"),
    ):
        monkeypatch.setattr(pii, name, value)

    def refuse(*args, **kwargs):
        raise OSError("model missing")

    fake_spacy.load = refuse
    pii.main()
    record = json.loads((redacted / "_stage_record.json").read_text(encoding="utf-8"))
    assert record["name_detection_available"] is False
    assert record["name_detection_error"] == "OSError: model missing"
    assert record["pii_entities_redacted"] == 1, "the regex rules still ran"
