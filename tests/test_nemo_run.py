"""Running real NeMo Curator on chunks. NeMo itself is not installed in the test environment, so a stand-in engine plays
its part: these tests cover everything around it (inputs, outputs, errors, the library and command line wiring)."""

import json
import shutil
from pathlib import Path

import pytest

from pipeline import api, cli, nemo_run, run

SAMPLE = "fiu_india_brochure.pdf"


class FakeEngine:
    """Fails every chunk whose text contains 'bad' (one filter) and 'worse' (two filters), like NeMo's score_chunks."""

    def __init__(self):
        self.calls = []

    def score_chunks(self, chunks, chunks_path):
        self.calls.append((chunks, Path(chunks_path).read_text(encoding="utf-8")))
        failed = {}
        for chunk in chunks:
            if "worse" in chunk["text"]:
                failed[chunk["chunk_id"]] = ["word_count", "numbers"]
            elif "bad" in chunk["text"]:
                failed[chunk["chunk_id"]] = ["word_count"]
        return {
            "failed_by": failed,
            "seconds": 1.5,
            "version": "1.3.0-fake",
            "filters": [{"key": "word_count", "label": "Word count", "removed": 2}],
        }


def write_chunks(path: Path, rows: list) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


CHUNKS = [
    {"chunk_id": "a__0", "doc_id": "a", "text": "a perfectly fine chunk"},
    {"chunk_id": "a__1", "doc_id": "a", "text": "this one is bad"},
    {"chunk_id": "b__0", "doc_id": "b", "text": "this one is worse"},
]


def test_chunks_are_normalised_from_chunk_files_and_from_curated_lines():
    curated = [{"text": "t1", "metadata": {"chunk_id": "x__0"}}, {"text": "t2", "metadata": {}}]
    assert nemo_run.normalise(CHUNKS)[1] == {"chunk_id": "a__1", "text": "this one is bad"}
    assert nemo_run.normalise(curated) == [{"chunk_id": "x__0", "text": "t1"}, {"chunk_id": "row-1", "text": "t2"}]


@pytest.mark.parametrize(
    "rows, message",
    [
        ([{"chunk_id": "a"}], "no text"),
        (["not an object"], "no text"),
        ([{"chunk_id": "a", "text": "x"}, {"chunk_id": "a", "text": "y"}], "Duplicate"),
    ],
)
def test_malformed_chunks_are_refused_with_a_reason(rows, message):
    with pytest.raises(ValueError, match=message):
        nemo_run.normalise(rows)


def test_run_writes_kept_and_removed_chunks_with_the_filters_they_failed(tmp_path):
    engine = FakeEngine()
    source = write_chunks(tmp_path / "chunks.jsonl", CHUNKS)
    report = nemo_run.run(source, tmp_path / "out", engine=engine)

    out = tmp_path / "out"
    kept = [json.loads(line) for line in (out / nemo_run.KEPT_NAME).read_text(encoding="utf-8").splitlines()]
    removed = [json.loads(line) for line in (out / nemo_run.REMOVED_NAME).read_text(encoding="utf-8").splitlines()]
    assert kept == [CHUNKS[0]]  # the original row, untouched
    assert [r["chunk_id"] for r in removed] == ["a__1", "b__0"]
    assert removed[0]["nemo_failed_filters"] == ["word_count"]
    assert removed[1]["nemo_failed_filters"] == ["word_count", "numbers"]
    assert removed[1]["text"] == "this one is worse"  # the original fields are kept beside the reasons
    assert report == json.loads((out / nemo_run.REPORT_NAME).read_text(encoding="utf-8"))
    assert (report["input_chunks"], report["kept"], report["removed"]) == (3, 1, 2)
    assert report["nemo_curator_version"] == "1.3.0-fake" and report["pipeline_seconds"] == 1.5


def test_the_engine_gets_normalised_chunks_and_a_file_of_them(tmp_path):
    engine = FakeEngine()
    curated = [{"text": "plain text", "metadata": {"chunk_id": "c__0", "doc_id": "c"}}]
    nemo_run.run(write_chunks(tmp_path / "curated.jsonl", curated), tmp_path / "out", engine=engine)
    chunks, prepared = engine.calls[0]
    assert chunks == [{"chunk_id": "c__0", "text": "plain text"}]
    assert json.loads(prepared.splitlines()[0]) == {"chunk_id": "c__0", "text": "plain text"}


def test_a_missing_or_empty_chunks_file_is_refused_before_nemo_is_needed(tmp_path):
    with pytest.raises(FileNotFoundError, match="not found"):
        nemo_run.run(tmp_path / "nope.jsonl", tmp_path / "out")
    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n", encoding="utf-8")
    with pytest.raises(ValueError, match="No chunks"):
        nemo_run.run(empty, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_availability_says_so_when_nemo_curator_is_not_installed(monkeypatch):
    monkeypatch.setattr(nemo_run.importlib.util, "find_spec", lambda name: None)
    assert "not installed" in nemo_run.unavailable_reason() and "requirements-nemo.txt" in nemo_run.unavailable_reason()
    monkeypatch.setattr(nemo_run.importlib.util, "find_spec", lambda name: object())
    assert nemo_run.unavailable_reason() is None


def test_the_nemo_command_reports_a_missing_install_with_exit_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(nemo_run, "unavailable_reason", lambda: "Real NeMo Curator is not installed here; do X.")
    assert cli.main(["nemo", str(tmp_path / "c.jsonl"), "-o", str(tmp_path / "out")]) == 1
    assert "not installed here" in capsys.readouterr().err


def test_the_nemo_command_reports_a_missing_file_with_exit_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(nemo_run, "unavailable_reason", lambda: None)
    assert cli.main(["nemo", str(tmp_path / "nope.jsonl"), "-o", str(tmp_path / "out")]) == 2
    assert "not found" in capsys.readouterr().err


def test_the_nemo_command_prints_the_result(monkeypatch, capsys):
    report = {
        "nemo_curator_version": "1.3.0",
        "executor": "XennaExecutor (CPU)",
        "pipeline_seconds": 9.0,
        "input_chunks": 3,
        "kept": 1,
        "removed": 2,
        "filters": [{"key": "a", "label": "Word count", "removed": 2}, {"key": "b", "label": "Numbers", "removed": 0}],
    }
    monkeypatch.setattr(nemo_run, "unavailable_reason", lambda: None)
    monkeypatch.setattr(nemo_run, "run", lambda chunks, out: report)
    assert cli.main(["nemo", "c.jsonl", "-o", "out"]) == 0
    printed = capsys.readouterr().out
    assert "NeMo Curator 1.3.0" in printed and "kept: 1  removed: 2" in printed and "Word count" in printed
    assert "Numbers" not in printed  # filters that removed nothing are left out


def copy_sample(tmp_path: Path) -> Path:
    inputs = tmp_path / "in"
    inputs.mkdir()
    shutil.copy(run.ROOT / "data" / "raw" / SAMPLE, inputs / SAMPLE)
    return inputs


def test_curate_refuses_nemo_before_running_when_it_is_not_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(nemo_run, "unavailable_reason", lambda: "Real NeMo Curator is not installed here.")
    with pytest.raises(RuntimeError, match="not installed"):
        api.curate(copy_sample(tmp_path), tmp_path / "out", nemo=True)
    assert not (tmp_path / "out").exists()


def test_curate_with_nemo_runs_it_on_the_chunks_our_quality_stage_received(tmp_path, monkeypatch):
    seen = {}

    def fake_compare(chunks_path, curated_path, out_path):
        seen["chunks"] = Path(chunks_path).read_text(encoding="utf-8").splitlines()
        seen["curated"] = Path(curated_path).read_text(encoding="utf-8").splitlines()
        Path(out_path).write_text("{}", encoding="utf-8")

    monkeypatch.setattr(nemo_run, "unavailable_reason", lambda: None)
    monkeypatch.setattr(nemo_run, "compare_with_ours", fake_compare)
    result = api.curate(copy_sample(tmp_path), tmp_path / "out", device="cpu", nemo=True)

    assert (tmp_path / "out" / "nemo_comparison.json").is_file()
    assert len(seen["curated"]) == result.summary["final_output_chunks"]
    assert len(seen["chunks"]) >= len(seen["curated"])  # the chunks that entered quality are a superset of those kept


def test_curate_without_nemo_never_touches_it(tmp_path, monkeypatch):
    def must_not_run(*args):
        raise AssertionError("NeMo was called although --nemo was not given")

    monkeypatch.setattr(nemo_run, "compare_with_ours", must_not_run)
    api.curate(copy_sample(tmp_path), tmp_path / "out", device="cpu")
    assert not (tmp_path / "out" / "nemo_comparison.json").exists()


def test_nemo_needs_an_output_folder():
    with pytest.raises(ValueError, match="output folder"):
        api.run_isolated(nemo=True)


def test_the_nemo_flag_reaches_curate(monkeypatch):
    seen = {}

    def fake_curate(pdf_dir, output, device, **options):
        seen.update(options)
        summary = {"stages": [], "final_output_chunks": 1, "pii_entities_redacted": 0}
        return api.CurateResult(summary, Path("out/curated.jsonl"), Path("out/pipeline_summary.json"), "cpu", "")

    monkeypatch.setattr(api, "curate", fake_curate)
    assert cli.main(["run", "in", "-o", "out", "--nemo"]) == 0
    assert seen["nemo"] is True
    cli.main(["run", "in", "-o", "out"])
    assert seen["nemo"] is False
