"""Self-check for the quality-classifier SIGNAL, with a stub scorer (no model, torch or
transformers needed).

Run: python -m pipeline.test_quality_signal
The signal must never remove a chunk, must be off by default, must key its cache by
SHA-256 of the chunk text, and must degrade cleanly when the model is unavailable.
"""
import contextlib
import hashlib
import io
import json
import tempfile
from pathlib import Path

from pipeline import quality

GOOD = (
    "The reporting entity shall verify the identity of every customer before opening an account "
    "and must keep the supporting records for five years after the closure of the relationship "
    "with the bank, as required under the rules issued by the regulator."
)
JUNKY = GOOD.replace("reporting entity", "reporting junk entity")  # passes the heuristics too


def run_quality(workdir: Path, texts: list, mode: str, scorer):
    """Run quality.main() on `texts` in an isolated folder with a stub scorer; returns
    (output chunks, stage record, number of scorer calls)."""
    calls = []

    def stub(text):
        calls.append(text)
        return scorer(text)

    saved = {name: getattr(quality, name) for name in (
        "IN_PATH", "OUT_PATH", "FILTERED_DIR", "STAGE_RECORD_PATH", "QUALITY_SIGNAL_CACHE_PATH",
        "QUALITY_SIGNAL_MODE", "_classifier_label")}
    try:
        quality.FILTERED_DIR = workdir / "filtered"
        quality.IN_PATH = workdir / "in.jsonl"
        quality.OUT_PATH = quality.FILTERED_DIR / "chunks.jsonl"
        quality.STAGE_RECORD_PATH = quality.FILTERED_DIR / "_stage_record.json"
        quality.QUALITY_SIGNAL_CACHE_PATH = workdir / "quality_signal_cache.json"
        quality.QUALITY_SIGNAL_MODE = mode
        quality._classifier_label = stub
        with quality.IN_PATH.open("w", encoding="utf-8") as f:
            for i, text in enumerate(texts):
                f.write(json.dumps({"chunk_id": f"d__{i}", "doc_id": "d", "source_file": "d.pdf", "text": text}) + "\n")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            quality.main()
        out = [json.loads(line) for line in quality.OUT_PATH.read_text(encoding="utf-8").splitlines()]
        record = json.loads(quality.STAGE_RECORD_PATH.read_text(encoding="utf-8"))
        return out, record, len(calls)
    finally:
        for name, value in saved.items():
            setattr(quality, name, value)


def label_of(text: str) -> str:
    return "Low" if "junk" in text else "High"


def main():
    assert quality.QUALITY_SIGNAL_MODE == "off", "the signal must be off by default"
    assert quality.USE_REAL_QUALITY_CLASSIFIER is False, "the classifier must never be a default filter"

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        cache_path = work / "quality_signal_cache.json"

        # --- off: no labels, no model call, the cache is not even created -----------------
        out, record, calls = run_quality(work, [GOOD, JUNKY], "off", label_of)
        assert calls == 0 and not cache_path.exists()
        assert [c["quality_classifier_label"] for c in out] == [None, None]
        assert record["quality_signal_mode"] == "off" and record["quality_signal_labels"] == {}

        # --- model: labels added, nothing removed (even "Low"), cache keyed by SHA-256 ----
        out, record, calls = run_quality(work, [GOOD, JUNKY], "model", label_of)
        assert calls == 2 and len(out) == 2, "a 'Low' label must not remove the chunk"
        assert [c["quality_classifier_label"] for c in out] == ["High", "Low"]
        assert record["docs_in"] == record["docs_out"] == 2 and record["removed"] == 0
        assert record["quality_signal_labels"] == {"High": 1, "Low": 1}
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        assert cache == {hashlib.sha256(GOOD.encode()).hexdigest(): "High",
                         hashlib.sha256(JUNKY.encode()).hexdigest(): "Low"}

        # --- model again: everything is a cache hit, the model is not called --------------
        out, _, calls = run_quality(work, [JUNKY, GOOD], "model", label_of)
        assert calls == 0 and [c["quality_classifier_label"] for c in out] == ["Low", "High"]

        # --- cache mode: hits get labels, misses are null, the model is never called ------
        fresh = GOOD.replace("five years", "seven years")
        out, record, calls = run_quality(work, [GOOD, fresh], "cache", label_of)
        assert calls == 0
        assert [c["quality_classifier_label"] for c in out] == ["High", None]
        assert record["quality_signal_labels"] == {"High": 1, "unavailable": 1}

        # --- model unavailable (e.g. transformers missing): run completes, tried only once -
        def broken(_text):
            raise ImportError("No module named 'transformers'")

        other = work / "second"
        other.mkdir()
        out, record, calls = run_quality(other, [GOOD, JUNKY, fresh], "model", broken)
        assert len(out) == 3 and all(c["quality_classifier_label"] is None for c in out)
        assert calls == 1, "after the first failure the model is not retried per chunk"
        assert record["quality_signal_model_error"].startswith("ImportError")
        assert record["quality_signal_labels"] == {"unavailable": 3}

    print("ok: signal is off by default, never removes chunks, SHA-256 cache, degrades cleanly")


if __name__ == "__main__":
    main()
