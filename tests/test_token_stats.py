"""Tests for token_stats module.

Validates grouping, chunk counting, total sums, strict line-numbered failure on
malformed JSON or missing fields, atomic file writing on failure, and tokenizer labels.
"""
import json
from pathlib import Path

import pytest

from pipeline.token_stats import compute_token_stats, main, resolve_tokenizer


def test_grouping_totals_and_chunk_counts():
    records = [
        {"text": "one two three four five", "metadata": {"source_file": "doc_a.pdf"}},
        {"text": "six seven eight", "metadata": {"source_file": "doc_a.pdf"}},
        {"text": "nine ten eleven twelve", "metadata": {"source_file": "doc_b.pdf"}},
    ]
    stats = compute_token_stats(records, tokenizer="words")
    assert stats["tokenizer"] == "words"

    doc_map = {d["source_file"]: d for d in stats["per_document"]}
    assert set(doc_map.keys()) == {"doc_a.pdf", "doc_b.pdf"}

    assert doc_map["doc_a.pdf"]["chunks"] == 2
    assert doc_map["doc_a.pdf"]["tokens"] == 8

    assert doc_map["doc_b.pdf"]["chunks"] == 1
    assert doc_map["doc_b.pdf"]["tokens"] == 4

    assert stats["total_tokens"] == 12
    assert stats["total_tokens"] == sum(d["tokens"] for d in stats["per_document"])


def test_malformed_json_fails_with_line_number():
    lines = [
        json.dumps({"text": "valid chunk 1", "metadata": {"source_file": "doc_1.pdf"}}),
        "{this is not valid json!@@#",
        json.dumps({"text": "valid chunk 2", "metadata": {"source_file": "doc_1.pdf"}}),
    ]

    with pytest.raises(ValueError) as exc_info:
        compute_token_stats(lines, tokenizer="words")

    err_msg = str(exc_info.value)
    assert "Line 2" in err_msg, f"Expected 'Line 2' in error message: {err_msg}"
    assert "malformed JSON" in err_msg


def test_missing_text_fails_with_line_number():
    lines = [
        json.dumps({"text": "valid chunk 1", "metadata": {"source_file": "doc_1.pdf"}}),
        json.dumps({"metadata": {"source_file": "doc_2.pdf"}}),
    ]

    with pytest.raises(ValueError) as exc_info:
        compute_token_stats(lines, tokenizer="words")

    err_msg = str(exc_info.value)
    assert "Line 2" in err_msg, f"Expected 'Line 2' in error message: {err_msg}"
    assert "missing required 'text'" in err_msg


def test_missing_metadata_fails_with_line_number():
    lines = [
        json.dumps({"text": "valid chunk 1", "metadata": {"source_file": "doc_1.pdf"}}),
        json.dumps({"text": "valid chunk 2"}),
    ]

    with pytest.raises(ValueError) as exc_info:
        compute_token_stats(lines, tokenizer="words")

    err_msg = str(exc_info.value)
    assert "Line 2" in err_msg, f"Expected 'Line 2' in error message: {err_msg}"
    assert "missing required 'metadata'" in err_msg


def test_missing_source_file_fails_with_line_number():
    lines = [
        json.dumps({"text": "valid chunk 1", "metadata": {"source_file": "doc_1.pdf"}}),
        json.dumps({"text": "valid chunk 2", "metadata": {"source_file": "doc_1.pdf"}}),
        json.dumps({"text": "valid chunk 3", "metadata": {"doc_id": "doc_3"}}),
    ]

    with pytest.raises(ValueError) as exc_info:
        compute_token_stats(lines, tokenizer="words")

    err_msg = str(exc_info.value)
    assert "Line 3" in err_msg, f"Expected 'Line 3' in error message: {err_msg}"
    assert "missing required 'source_file'" in err_msg


def test_atomic_write_preserves_previous_file_on_failure(tmp_path: Path):
    input_file = tmp_path / "broken.jsonl"
    output_file = tmp_path / "token_stats.json"

    # Write initial valid output file
    initial_content = json.dumps({"status": "previous_valid_data"}, indent=2) + "\n"
    output_file.write_text(initial_content, encoding="utf-8")

    # Broken input: valid line then broken line
    broken_lines = [
        json.dumps({"text": "valid chunk", "metadata": {"source_file": "doc.pdf"}}),
        "broken non-json line",
    ]
    input_file.write_text("\n".join(broken_lines) + "\n", encoding="utf-8")

    # Execution must fail
    with pytest.raises(ValueError):
        main(["-i", str(input_file), "-o", str(output_file)])

    # Output file must remain intact and identical to initial content
    assert output_file.is_file()
    assert output_file.read_text(encoding="utf-8") == initial_content

    # No leftover temporary files
    leftovers = list(tmp_path.glob(".*tmp*"))
    assert leftovers == [], f"Found leftover temp files: {leftovers}"


def test_fallback_to_words():
    name, fn = resolve_tokenizer("words")
    assert name == "words"
    text = "alpha beta   gamma\ndelta"
    assert fn(text) == 4

    stats = compute_token_stats(
        [{"text": text, "metadata": {"source_file": "test.pdf"}}],
        tokenizer="words",
    )
    assert stats["tokenizer"] == "words"
    assert stats["total_tokens"] == 4


def test_tiktoken_label_and_encoding():
    name, fn = resolve_tokenizer("cl100k_base")
    assert name == "tiktoken:cl100k_base"
    text = "KYC and Anti-Money Laundering directions"
    tokens = fn(text)
    assert tokens > 0

    stats = compute_token_stats(
        [{"text": text, "metadata": {"source_file": "kyc.pdf"}}],
        tokenizer="cl100k_base",
    )
    assert stats["tokenizer"] == "tiktoken:cl100k_base"
    assert stats["total_tokens"] == tokens


def test_cli_execution(tmp_path: Path):
    input_file = tmp_path / "sample.jsonl"
    output_file = tmp_path / "token_stats.json"

    records = [
        {"text": "Sample regulatory chunk 1", "metadata": {"source_file": "rbi_1.pdf"}},
        {"text": "Sample regulatory chunk 2", "metadata": {"source_file": "rbi_2.pdf"}},
    ]
    input_file.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

    ret = main(["-i", str(input_file), "-o", str(output_file), "--tokenizer", "words"])
    assert ret == 0
    assert output_file.is_file()

    data = json.loads(output_file.read_text(encoding="utf-8"))
    assert data["tokenizer"] == "words"
    assert data["total_tokens"] == 8
    assert len(data["per_document"]) == 2
    assert sum(d["chunks"] for d in data["per_document"]) == 2


if __name__ == "__main__":
    test_grouping_totals_and_chunk_counts()
    test_malformed_json_fails_with_line_number()
    test_missing_text_fails_with_line_number()
    test_missing_metadata_fails_with_line_number()
    test_missing_source_file_fails_with_line_number()
    test_fallback_to_words()
    test_tiktoken_label_and_encoding()
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        test_atomic_write_preserves_previous_file_on_failure(Path(tmp))
        test_cli_execution(Path(tmp))
    print("ok: all token_stats unit tests passed")
