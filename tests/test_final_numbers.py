"""Tests for scripts/make_final_numbers.py: every number comes from a snapshot, nothing is invented."""

import importlib.util
import json
import shutil
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


@pytest.fixture
def readme(tmp_path):
    """A temporary README with the two marker lines around stale text."""
    path = tmp_path / "README.md"
    path.write_text(f"intro\n\n{numbers.README_START}\n\nstale\n\n{numbers.README_END}\n\noutro\n", encoding="utf-8")
    return path


def run_main(copy, out, readme, *extra):
    return numbers.main(["--snapshots", str(copy), "--out", str(out), "--readme", str(readme), *extra])


def test_main_writes_both_files_with_unix_line_endings(copy, readme, tmp_path):
    out = tmp_path / "FINAL_NUMBERS.md"
    assert run_main(copy, out, readme) == 0
    data = out.read_bytes()
    assert data.startswith(b"# Final numbers") and b"\r" not in data
    assert data.decode("utf-8") == numbers.build(copy)
    text = readme.read_text(encoding="utf-8")
    assert text.startswith("intro\n") and text.endswith("outro\n") and "stale" not in text
    assert numbers.readme_block(copy) in text and "\r" not in text


def test_the_readme_table_equals_the_snapshots():
    summary, tokens, doctypes, nemo = (read(name) for name in FILES)
    block = numbers.readme_block(SNAPSHOTS)

    assert f"{summary['final_output_chunks']:,} (" in block
    assert f"| Personal-data items hidden | {summary['pii_entities_redacted']:,} (" in block
    assert f"{tokens['total_tokens']:,}" in block
    assert f"{100 * doctypes['accuracy']['by_family']:.1f}%" in block
    assert f"{nemo['nemo']['removed']:,} (" in block and f"{nemo['ours']['removed']:,} (" in block
    for bad in ("None", "nan", "undefined", "n/a"):
        assert bad not in block, bad


def test_the_committed_readme_and_final_numbers_are_up_to_date():
    # Fails when a snapshot changed and `python scripts/make_final_numbers.py` was not run.
    assert numbers.main(["--check"]) == 0


def test_check_reports_a_stale_file_and_writes_nothing(copy, readme, tmp_path, capsys):
    out = tmp_path / "FINAL_NUMBERS.md"
    before = readme.read_bytes()
    assert run_main(copy, out, readme, "--check") == 1
    assert "out of date" in capsys.readouterr().out
    assert readme.read_bytes() == before and not out.exists()

    run_main(copy, out, readme)
    assert run_main(copy, out, readme, "--check") == 0


def test_updating_the_readme_twice_changes_nothing(copy, readme, tmp_path):
    out = tmp_path / "FINAL_NUMBERS.md"
    run_main(copy, out, readme)
    first = readme.read_bytes()
    run_main(copy, out, readme)
    assert readme.read_bytes() == first


def test_a_readme_without_markers_is_refused():
    with pytest.raises(ValueError, match="marker"):
        numbers.update_readme("no markers here", "table")
    with pytest.raises(ValueError, match="marker"):
        numbers.update_readme(f"{numbers.README_END}\n{numbers.README_START}", "table")
