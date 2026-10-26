"""The run manifest and the audit log: what ran, on which inputs, producing which outputs."""

import hashlib
import json
from pathlib import Path

import pytest

from pipeline import __version__, run
from pipeline.api import curate

SAMPLE = "fiu_india_brochure.pdf"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def finished(tmp_path_factory):
    """One real run on one real PDF, shared by the tests that only read its results."""
    base = tmp_path_factory.mktemp("manifest")
    pdfs, out = base / "pdfs", base / "out"
    pdfs.mkdir()
    (pdfs / SAMPLE).write_bytes((run.ROOT / "data" / "raw" / SAMPLE).read_bytes())
    result = curate(pdfs, out, device="cpu")
    return pdfs, out, result


def read_manifest(out: Path) -> dict:
    return json.loads((out / "manifest.json").read_text(encoding="utf-8"))


def test_the_manifest_records_inputs_and_outputs_with_their_hashes(finished):
    pdfs, out, result = finished
    manifest = read_manifest(out)

    assert manifest["manifest_version"] == 1
    assert manifest["tool"]["name"] == "bfsi-curate" and manifest["tool"]["version"] == __version__
    assert manifest["inputs"] == [
        {"name": SAMPLE, "bytes": (pdfs / SAMPLE).stat().st_size, "sha256": sha256(pdfs / SAMPLE)}
    ]
    outputs = {o["name"]: o for o in manifest["outputs"]}
    assert outputs["curated.jsonl"]["sha256"] == sha256(out / "curated.jsonl")
    assert outputs["curated.jsonl"]["records"] == result.summary["final_output_chunks"]
    assert outputs["pipeline_summary.json"]["sha256"] == sha256(out / "pipeline_summary.json")
    assert result.manifest_path == out / "manifest.json"


def test_the_manifest_records_the_options_and_the_stage_counts(finished):
    _, out, result = finished
    manifest = read_manifest(out)

    assert manifest["run"]["device"] == "cpu"
    assert manifest["run"]["pii_engine"] == "regex" and manifest["run"]["quality_signal"] == "off"
    assert manifest["run"]["name_detection_available"] is result.summary["name_detection_available"]
    assert [s["stage"] for s in manifest["stages"]][0] == "extract"
    assert manifest["stages"][-1]["docs_out"] == result.summary["final_output_chunks"]
    assert manifest["run"]["duration_seconds"] >= 0 and manifest["run"]["run_id"]


def test_the_manifest_does_not_leak_folder_names(finished):
    pdfs, out, _ = finished
    text = (out / "manifest.json").read_text(encoding="utf-8")
    assert str(pdfs) not in text and str(out) not in text


def test_the_audit_log_has_a_started_and_a_finished_line_for_the_run(finished):
    _, out, _ = finished
    events = [json.loads(line) for line in (out / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [e["event"] for e in events] == ["started", "finished"]
    assert events[0]["run_id"] == events[1]["run_id"] == read_manifest(out)["run"]["run_id"]
    assert events[0]["user"] and events[1]["chunks"] == read_manifest(out)["outputs"][0]["records"]


def test_a_second_run_appends_to_the_audit_log_and_keeps_the_curated_file_identical(finished):
    pdfs, out, _ = finished
    before = sha256(out / "curated.jsonl")
    curate(pdfs, out, device="cpu")
    events = [json.loads(line) for line in (out / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [e["event"] for e in events] == ["started", "finished", "started", "finished"]
    assert len({e["run_id"] for e in events}) == 2
    assert sha256(out / "curated.jsonl") == before


def test_a_run_that_stops_is_audited_as_failed_and_leaves_no_manifest(tmp_path):
    pdfs, out = tmp_path / "pdfs", tmp_path / "out"
    pdfs.mkdir()
    (pdfs / "broken.pdf").write_bytes(b"this is not a pdf")
    with pytest.raises(RuntimeError):
        curate(pdfs, out, device="cpu")
    events = [json.loads(line) for line in (out / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [e["event"] for e in events] == ["started", "failed"]
    assert "extract" in events[1]["error"]
    assert not (out / "manifest.json").exists()


def test_a_bad_input_folder_is_refused_before_anything_is_written(tmp_path):
    with pytest.raises(FileNotFoundError):
        curate(tmp_path / "nope", tmp_path / "out")
    assert not (tmp_path / "out").exists()
