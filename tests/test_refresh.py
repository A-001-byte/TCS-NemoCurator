"""Tests for the dashboard snapshot refresh: masked examples, no leaked paths, all-or-nothing publish."""

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline import refresh_snapshots as rs
from pipeline.api import curate

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ("bank_of_baroda_kyc.pdf", "fiu_india_brochure.pdf", "rbi_kyc_fidcindia_aug2025.pdf")

# Independent of the pipeline's own patterns on purpose: the tests must not agree with a bug there.
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
MOBILE = re.compile(r"(?<!\d)[6-9]\d{9}(?!\d)")
LOCAL_PATH = re.compile(r"[A-Za-z]:\\|/home/|/tmp/|/Users/|kyc_run_|dashboard_refresh_")


def revealed(masked: str) -> int:
    return sum(char.isalnum() for char in masked)


def test_mask_value_hides_most_of_a_value_but_keeps_its_shape():
    assert rs.mask_value("EMAIL", "jsctcr-mha@gov.in") == "js****-***@gov.in"
    assert rs.mask_value("PINCODE", "110001") == "11****"
    assert rs.mask_value("PHONE", "+91 9820320181") == "+91 **********"
    assert rs.mask_value("SWIFT_BIC", "BARBINBBXXX") == "BA*********"
    assert rs.mask_value("EMAIL", "a@b.in") == "*@b.in", "a very short value is hidden completely"
    for value in ("abc", "abcdef", "x" * 40, "12 34 56 78 90 12"):
        assert revealed(rs.mask_value("OTHER", value)) <= rs.VISIBLE_CHARS
        assert revealed(rs.mask_value("OTHER", value)) <= len(value) // 3


def test_mask_example_keeps_identity_fields_and_redacts_the_neighbours():
    example = {
        "doc_id": "doc_a",
        "entity_type": "EMAIL",
        "before": "officer@bank.example.in",
        "context_before": "call 9820320181 or write to ",
        "context_after": " , copy to cc@bank.example.in now",
    }
    masked = rs.mask_example(example)

    assert masked["doc_id"] == "doc_a" and masked["entity_type"] == "EMAIL"
    assert masked["before"] != example["before"] and masked["before"].endswith("@bank.example.in")
    assert not EMAIL.search(masked["before"])
    assert "9820320181" not in masked["context_before"] and "[REDACTED_PHONE]" in masked["context_before"]
    assert "cc@bank" not in masked["context_after"] and "[REDACTED_EMAIL]" in masked["context_after"]
    assert example["before"] == "officer@bank.example.in", "the input must not be changed"


def test_absolute_paths_become_file_names_and_relative_paths_stay():
    data = {
        "stages": [
            {"output_path": "C:\\Users\\someone\\AppData\\Local\\Temp\\kyc_run_x\\data\\output\\curated.jsonl"},
            {"output_path": "/home/someone/repo/data/output/curated.jsonl"},
            {"output_path": "data/output/curated.jsonl"},
        ],
        "ratio": 0.5,
    }
    cleaned = rs.without_local_paths(data)
    assert [stage["output_path"] for stage in cleaned["stages"]] == [
        "curated.jsonl",
        "curated.jsonl",
        "data/output/curated.jsonl",
    ]
    assert cleaned["ratio"] == 0.5
    assert data["stages"][0]["output_path"].startswith("C:"), "the input must not be changed"


def test_find_residual_pii_flags_what_the_pipeline_would_still_redact():
    assert rs.find_residual_pii("write to someone@bank.example.in") == {"EMAIL": 1}
    assert rs.find_residual_pii("The reporting entity shall verify the customer.") == {}
    assert rs.find_residual_pii("write to [REDACTED_EMAIL] about [REDACTED_PINCODE]") == {}


def write_curated(path: Path, texts: list) -> None:
    rows = [
        {"text": text, "metadata": {"chunk_id": f"c{i}", "doc_id": "d", "source_file": "d.pdf"}}
        for i, text in enumerate(texts)
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_publish_refuses_when_the_curated_output_still_has_personal_data(tmp_path):
    curated = tmp_path / "curated.jsonl"
    write_curated(curated, ["clean text", "write to someone@bank.example.in"])
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="nothing was published"):
        rs.publish_snapshots({"pii_examples": []}, curated, out)
    assert not out.exists() or not any(out.iterdir())


def test_publish_writes_both_files_unchanged_and_leaves_no_temporary_files(tmp_path):
    curated = tmp_path / "curated.jsonl"
    write_curated(curated, ["The bank shall keep records for five years.", "Hello [REDACTED_EMAIL]"])
    summary = {
        "stages": [{"stage": "output", "output_path": "C:\\Users\\someone\\x\\curated.jsonl"}],
        "pii_examples": [
            {
                "doc_id": "d",
                "entity_type": "EMAIL",
                "before": "officer@bank.example.in",
                "context_before": "to ",
                "context_after": " now",
            }
        ],
    }
    out = tmp_path / "out"
    published = rs.publish_snapshots(summary, curated, out)

    assert (out / "curated.jsonl").read_bytes() == curated.read_bytes()
    on_disk = json.loads((out / "pipeline_summary.json").read_text(encoding="utf-8"))
    assert on_disk == published
    assert on_disk["stages"][0]["output_path"] == "curated.jsonl"
    assert on_disk["pii_examples"][0]["before"].endswith("@bank.example.in")
    assert on_disk["pii_examples"][0]["before"] != "officer@bank.example.in"
    assert sorted(path.name for path in out.iterdir()) == ["curated.jsonl", "pipeline_summary.json"]
    assert summary["pii_examples"][0]["before"] == "officer@bank.example.in", "the input must not be changed"


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        (False, ("auto", "off")),
        (True, ("cuda", "model")),
    ],
)
def test_refresh_uses_configured_quality_device_and_default_pii(tmp_path, monkeypatch, configured, expected):
    pdfs = tmp_path / "pdfs"
    pdfs.mkdir()
    (pdfs / "sample.pdf").write_bytes(b"%PDF")
    output_dir = tmp_path / "snapshots"
    seen = {}

    if configured:
        monkeypatch.setenv(rs.REFRESH_DEVICE_ENV, "cuda")
        monkeypatch.setenv(rs.REFRESH_QUALITY_SIGNAL_ENV, "model")
    else:
        monkeypatch.delenv(rs.REFRESH_DEVICE_ENV, raising=False)
        monkeypatch.delenv(rs.REFRESH_QUALITY_SIGNAL_ENV, raising=False)

    def fake_curate(input_dir, run_output, *, device, pii_engine, quality_signal):
        seen.update(device=device, pii_engine=pii_engine, quality_signal=quality_signal)
        run_output.mkdir()
        curated = run_output / "curated.jsonl"
        write_curated(curated, ["The bank shall keep records for five years."])
        summary = {
            "stages": [{"stage": "quality_filter", "device": "cuda:0" if configured else "cpu"}],
            "pii_examples": [],
            "pii_entities_redacted": 68,
            "final_output_chunks": 1,
        }
        return SimpleNamespace(summary=summary, output_path=curated, device=summary["stages"][0]["device"])

    monkeypatch.setattr(rs, "curate", fake_curate)
    published = rs.refresh(pdfs, output_dir)

    assert seen == {"device": expected[0], "pii_engine": "regex", "quality_signal": expected[1]}
    assert published["pii_entities_redacted"] == 68
    assert json.loads((output_dir / "pipeline_summary.json").read_text()) == published


def test_a_real_sample_publishes_the_pipeline_output_with_masked_examples(tmp_path):
    pdfs = tmp_path / "pdfs"
    pdfs.mkdir()
    for name in SAMPLES:
        (pdfs / name).write_bytes((ROOT / "data" / "raw" / name).read_bytes())
    result = curate(pdfs, tmp_path / "run", device="cpu")

    out = tmp_path / "snapshots"
    published = rs.publish_snapshots(result.summary, result.output_path, out)
    summary_text = (out / "pipeline_summary.json").read_text(encoding="utf-8")

    assert [stage["stage"] for stage in published["stages"]] == [
        "extract",
        "clean_langid",
        "heal",
        "dedup",
        "quality_filter",
        "pii_redact",
        "output",
    ]
    assert (out / "curated.jsonl").read_bytes() == result.output_path.read_bytes(), "output is published unchanged"
    assert published["final_output_chunks"] == len((out / "curated.jsonl").read_text(encoding="utf-8").splitlines())
    assert published["pii_entities_redacted"] == result.summary["pii_entities_redacted"] > 0
    assert not LOCAL_PATH.search(summary_text), LOCAL_PATH.search(summary_text)

    examples = published["pii_examples"]
    assert examples and all(example["doc_id"] and "*" in example["before"] for example in examples)
    for example in examples:
        for field in ("before", "context_before", "context_after"):
            assert not EMAIL.search(example[field]) or "*" in example[field], (field, example[field])
            assert not MOBILE.search(example[field]), (field, example[field])
    assert not MOBILE.search(summary_text)
