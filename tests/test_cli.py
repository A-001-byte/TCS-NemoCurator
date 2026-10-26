"""Tests for the bfsi-curate command line: exit codes, messages, flags, and the serve command."""

import logging
import threading
import urllib.request
from dataclasses import replace
from pathlib import Path

import pytest

from pipeline import __version__, api, cli, server


def fake_result(names_on: bool = True) -> api.CurateResult:
    summary = {
        "stages": [{"stage": "extract", "docs_in": 2, "docs_out": 2, "removed": 0}],
        "final_output_chunks": 7,
        "pii_entities_redacted": 3,
        "name_detection_available": names_on,
    }
    return api.CurateResult(summary, Path("out/curated.jsonl"), Path("out/pipeline_summary.json"), "cpu", "")


def test_version_flag_prints_the_version_and_exits_0(capsys):
    with pytest.raises(SystemExit) as stop:
        cli.main(["--version"])
    assert stop.value.code == 0
    assert capsys.readouterr().out.strip() == f"bfsi-curate {__version__}"


def test_a_missing_input_folder_is_exit_2_with_the_reason_on_stderr(tmp_path, capsys):
    assert cli.main(["run", str(tmp_path / "nope"), "-o", str(tmp_path / "out")]) == 2
    captured = capsys.readouterr()
    assert "Input folder not found" in captured.err and captured.out == ""


def test_a_folder_without_pdfs_is_exit_2(tmp_path, capsys):
    (tmp_path / "notes.txt").write_text("not a pdf")
    assert cli.main(["run", str(tmp_path), "-o", str(tmp_path / "out")]) == 2
    assert "No .pdf files" in capsys.readouterr().err


def test_a_folder_where_nothing_can_be_read_is_exit_1_with_a_one_line_reason(tmp_path, capsys):
    (tmp_path / "empty.pdf").write_bytes(b"")
    assert cli.main(["run", str(tmp_path), "-o", str(tmp_path / "out")]) == 1
    short = capsys.readouterr().err
    assert short.startswith("error: The pipeline stopped at the extract stage") and short.count("\n") == 1

    assert cli.main(["run", str(tmp_path), "-o", str(tmp_path / "out"), "--verbose"]) == 1
    assert "Pipeline stopped: stage 'extract' failed" in capsys.readouterr().err, "--verbose adds the pipeline's log"


def test_a_successful_run_prints_the_table_and_warns_when_name_detection_is_off(monkeypatch, capsys):
    monkeypatch.setattr(api, "curate", lambda *args, **kwargs: fake_result(names_on=False))
    assert cli.main(["run", "in", "-o", "out"]) == 0
    captured = capsys.readouterr()
    assert "chunks written: 7" in captured.out and "PII entities redacted: 3" in captured.out
    assert "warning: person-name detection is OFF" in captured.err


def test_no_warning_when_name_detection_is_on(monkeypatch, capsys):
    monkeypatch.setattr(api, "curate", lambda *args, **kwargs: fake_result(names_on=True))
    assert cli.main(["run", "in", "-o", "out"]) == 0
    assert capsys.readouterr().err == ""


def test_cuda_detection_with_default_stages_explains_no_model_uses_it(monkeypatch, capsys):
    monkeypatch.setattr(api, "curate", lambda *args, **kwargs: replace(fake_result(), device="cuda:0"))
    assert cli.main(["run", "in", "-o", "out"]) == 0
    assert "no GPU model is enabled" in capsys.readouterr().err


def test_optional_model_flags_reach_the_api(monkeypatch, capsys):
    seen = {}

    def capture(*args, **kwargs):
        seen.update(kwargs)
        return fake_result()

    monkeypatch.setattr(api, "curate", capture)
    assert (
        cli.main(
            [
                "run",
                "in",
                "-o",
                "out",
                "--device",
                "cuda",
                "--pii-engine",
                "gliner",
                "--quality-signal",
                "model",
            ]
        )
        == 0
    )
    assert seen == {"pii_engine": "gliner", "quality_signal": "model", "ocr": False}
    capsys.readouterr()


def test_ctrl_c_is_exit_130(monkeypatch, capsys):
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(api, "curate", interrupted)
    assert cli.main(["run", "in", "-o", "out"]) == 130
    assert "interrupted" in capsys.readouterr().err


def test_serve_hands_its_flags_to_the_server(monkeypatch):
    seen = []
    monkeypatch.setattr(server, "main", lambda argv: seen.append(argv) or 0)
    assert cli.main(["serve", "--host", "0.0.0.0", "--port", "9000"]) == 0
    assert cli.main(["serve"]) == 0
    assert seen == [["--host", "0.0.0.0", "--port", "9000"], []]


# --- the server's own start-up -------------------------------------------------------------------


def test_the_address_comes_from_flags_then_the_environment_then_the_defaults(monkeypatch):
    monkeypatch.delenv("CURATOR_HOST", raising=False)
    monkeypatch.delenv("CURATOR_PORT", raising=False)
    assert server._address([]) == ("127.0.0.1", 8000)
    monkeypatch.setenv("CURATOR_HOST", "10.0.0.5")
    monkeypatch.setenv("CURATOR_PORT", "9100")
    assert server._address([]) == ("10.0.0.5", 9100)
    assert server._address(["--host", "127.0.0.1", "--port", "9200"]) == ("127.0.0.1", 9200), "a flag wins"


@pytest.mark.parametrize(
    "argv,env", [(["--port", "0"], None), (["--port", "70000"], None), ([], "abc"), (["--port", "x"], None)]
)
def test_a_bad_port_is_a_usage_error(monkeypatch, argv, env):
    monkeypatch.delenv("CURATOR_PORT", raising=False)
    if env:
        monkeypatch.setenv("CURATOR_PORT", env)
    with pytest.raises(SystemExit) as stop:
        server._address(argv)
    assert stop.value.code == 2


def test_a_port_that_is_taken_is_exit_1_and_a_public_address_is_warned_about(monkeypatch, caplog):
    def taken(host, port):
        raise OSError("address already in use")

    monkeypatch.setattr(server, "make_server", taken)
    with caplog.at_level(logging.WARNING, logger="pipeline.server"):
        assert server.main(["--host", "0.0.0.0", "--port", "8123"]) == 1
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "no authentication" in messages and "Cannot listen on 0.0.0.0:8123" in messages


def test_the_server_starts_answers_and_shuts_down_cleanly(monkeypatch):
    made = []

    def make(host, port):
        httpd = server.ThreadingHTTPServer((host, 0), server.Handler)  # port 0: any free port
        made.append(httpd)
        return httpd

    monkeypatch.setattr(server, "make_server", make)
    result = []
    thread = threading.Thread(target=lambda: result.append(server.main(["--port", "8124"])))
    thread.start()
    try:
        for _ in range(200):
            if made:
                break
            threading.Event().wait(0.01)
        port = made[0].server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=5) as response:
            assert response.status == 200
    finally:
        made[0].shutdown()
        thread.join(5)
    assert result == [0] and not thread.is_alive()
