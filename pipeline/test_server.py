"""Self-check for the upload API's pipeline runner.

Run: venv/Scripts/python -m pipeline.test_server
"""
import base64
import json

from pipeline import extract, run
from pipeline.server import BadRequest, _decode_files, run_on_upload

SAMPLE = run.ROOT / "data" / "raw" / "bank_of_baroda_kyc.pdf"


def _rejects(payload, fragment):
    try:
        _decode_files(payload)
    except BadRequest as exc:
        assert fragment in str(exc), exc
    else:
        raise AssertionError(f"accepted {payload!r}")


def main():
    pdf = base64.b64encode(SAMPLE.read_bytes()).decode()
    _rejects({}, "at least one")
    _rejects({"files": [{"name": "notes.txt", "data": pdf}]}, "not a .pdf")
    _rejects({"files": [{"name": "x.pdf", "data": base64.b64encode(b"hello").decode()}]}, "not a valid PDF")
    assert _decode_files({"files": [{"name": "../../evil.pdf", "data": pdf}]})[0][0] == "evil.pdf"

    raw_dir_before = extract.RAW_DIR
    result, log = run_on_upload(_decode_files({"files": [{"name": SAMPLE.name, "data": pdf}]}))
    assert result, log
    assert extract.RAW_DIR == raw_dir_before, "module paths must be restored after a run"

    summary = result["summary"]
    rows = [json.loads(line) for line in result["curated_jsonl"].splitlines() if line.strip()]
    assert summary["stages"][0]["docs_in"] == 1
    assert len(rows) == summary["final_output_chunks"] > 0
    assert all(row["metadata"]["source_file"] == SAMPLE.name for row in rows)
    assert summary["pii_entities_redacted"] > 0, "this PDF has PIN codes and emails"
    assert "[REDACTED_" in result["curated_jsonl"]
    print(f"ok: {len(rows)} chunks, {summary['pii_entities_redacted']} PII entities redacted")


if __name__ == "__main__":
    main()
