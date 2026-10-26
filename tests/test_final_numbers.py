"""Tests for scripts/make_final_numbers.py: every number comes from a snapshot, nothing is invented."""
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOTS = ROOT / "dashboard" / "public"
FILES = ("pipeline_summary.json", "token_stats.json", "doctype_eval.json", "nemo_comparison.json")

spec = importlib.util.spec_from_file_location("make_final_numbers", ROOT / "scripts" / "make_final_numbers.py")
numbers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(numbers)


def read(name: str) -> dict:
    return json.loads((SNAPSHOTS / name).read_text(encoding="utf-8").lstrip("﻿"))


@pytest.fixture
def copy(tmp_path):
    """A temporary copy of the four snapshots to damage."""
    for name in FILES:
        shutil.copyfile(SNAPSHOTS / name, tmp_path / name)
    return tmp_path


def test_every_headline_number_equals_the_snapshot_it_comes_from():
    text = numbers.build(SNAPSHOTS)
    summary, tokens, doctypes, nemo = (read(name) for name in FILES)

    assert f"| Final curated chunks | {summary['final_output_chunks']:,} |" in text
    assert f"- Entities redacted: {summary['pii_entities_redacted']:,}" in text
    for kind, count in summary["pii_entity_type_counts"].items():
        assert f"| {kind} | {count:,} |" in text
    assert f"| Total tokens | {tokens['total_tokens']:,} |" in text
    assert f"| Right, whole near-copy family held out | {100 * doctypes['accuracy']['by_family']:.1f}% |" in text
    assert f"| Always guessing the biggest type | {100 * doctypes['majority_baseline']:.1f}% |" in text
    assert doctypes["caption"] in text
    assert f"{nemo['nemo']['removed']:,} (" in text and f"{nemo['ours']['removed']:,} (" in text
    for record in summary["stages"]:
        assert f"| {record['stage']} | {record['docs_in']:,} | {record['docs_out']:,} | {record['removed']:,} |" in text


def test_the_output_is_deterministic_and_has_no_placeholders_for_real_data():
    first = numbers.build(SNAPSHOTS)
    assert first == numbers.build(SNAPSHOTS)
    for bad in ("None", "nan", "undefined", "n/a", "Not available"):
        assert bad not in first, bad


def test_missing_optional_snapshots_are_reported_not_invented(copy):
    for name in FILES[1:]:
        (copy / name).unlink()
    text = numbers.build(copy)
    for section in ("token_stats.json", "doctype_eval.json", "nemo_comparison.json"):
        assert f"Not available ({section} is missing)" in text
    assert "## Corpus" in text and "## Stages" in text


def test_the_summary_is_required(copy):
    (copy / "pipeline_summary.json").unlink()
    with pytest.raises(FileNotFoundError, match="pipeline_summary.json"):
        numbers.build(copy)


def test_a_byte_order_mark_in_a_snapshot_is_ignored(copy):
    path = copy / "doctype_eval.json"
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    assert numbers.build(copy) == numbers.build(SNAPSHOTS)


def test_a_run_without_name_detection_or_device_says_so(copy):
    path = copy / "pipeline_summary.json"
    summary = json.loads(path.read_text(encoding="utf-8").lstrip("﻿"))
    summary["name_detection_available"] = False
    for record in summary["stages"]:
        record.pop("device", None)
    path.write_text(json.dumps(summary), encoding="utf-8")
    text = numbers.build(copy)
    assert "Name detection: OFF" in text
    assert "| Compute device (quality stage) | not reported |" in text


def test_main_writes_a_file_with_unix_line_endings(copy, tmp_path, monkeypatch):
    out = tmp_path / "FINAL_NUMBERS.md"
    monkeypatch.setattr(sys, "argv", ["make_final_numbers", "--snapshots", str(copy), "--out", str(out)])
    numbers.main()
    data = out.read_bytes()
    assert data.startswith(b"# Final numbers") and b"\r" not in data
    assert data.decode("utf-8") == numbers.build(copy)
