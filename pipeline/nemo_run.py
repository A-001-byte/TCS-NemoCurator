"""Run real NVIDIA NeMo Curator on a file of chunks, directly.

    bfsi-curate nemo CHUNKS.jsonl -o OUT/            run NeMo's filters on any chunks file
    bfsi-curate run pdfs/ -o out/ --nemo             our pipeline, then NeMo on the chunks it made

NeMo Curator is not part of the default install and does not install on native Windows: use Linux or WSL2 and
`pip install -r requirements-nemo.txt`. Everything that needs NeMo itself lives in `pipeline/nemo_compare.py`; this module
only prepares the chunks, calls it, and writes the results, so it can be tested without NeMo.

NeMo's filters run on the CPU. The GPU is only relevant to NeMo's own deduplication, which this does not run.
"""

import importlib
import importlib.util
import json
import tempfile
from pathlib import Path
from typing import Optional

INSTALL_HINT = "on Linux or WSL2 run: pip install -r requirements-nemo.txt"
KEPT_NAME, REMOVED_NAME, REPORT_NAME = "nemo_kept.jsonl", "nemo_removed.jsonl", "nemo_report.json"


def unavailable_reason() -> Optional[str]:
    """Why real NeMo Curator cannot run on this machine, as one sentence, or None when it can."""
    if importlib.util.find_spec("nemo_curator") is None:
        return f"Real NeMo Curator is not installed here; {INSTALL_HINT}."
    return None


def read_rows(path: Path) -> list:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Chunks file not found: {path}")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if not rows:
        raise ValueError(f"No chunks in {path}")
    return rows


def normalise(rows: list) -> list:
    """[{chunk_id, text}] for NeMo, from either chunk files ({chunk_id, text}) or curated lines ({text, metadata})."""
    chunks, seen = [], set()
    for position, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("text"), str):
            raise ValueError(f"Line {position + 1} has no text field")
        chunk_id = row.get("chunk_id") or (row.get("metadata") or {}).get("chunk_id") or f"row-{position}"
        if chunk_id in seen:
            raise ValueError(f"Duplicate chunk id: {chunk_id}")
        seen.add(chunk_id)
        chunks.append({"chunk_id": chunk_id, "text": row["text"]})
    return chunks


def _write_jsonl(path: Path, rows: list) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8", newline="\n")


def run(chunks_path, out_dir, engine=None) -> dict:
    """NeMo's filters on `chunks_path`; writes nemo_kept.jsonl, nemo_removed.jsonl (each with the filters it failed)
    and nemo_report.json into `out_dir`, and returns the report. `engine` defaults to pipeline.nemo_compare."""
    rows = read_rows(chunks_path)
    chunks = normalise(rows)
    engine = engine or importlib.import_module("pipeline.nemo_compare")
    with tempfile.TemporaryDirectory(prefix="nemo_run_") as tmp:
        prepared = Path(tmp) / "chunks.jsonl"
        _write_jsonl(prepared, chunks)
        scored = engine.score_chunks(chunks, prepared)

    failed_by = scored["failed_by"]
    kept, removed = [], []
    for row, chunk in zip(rows, chunks):
        failed = failed_by.get(chunk["chunk_id"])
        if failed:
            removed.append({**row, "nemo_failed_filters": failed})
        else:
            kept.append(row)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(out_dir / KEPT_NAME, kept)
    _write_jsonl(out_dir / REMOVED_NAME, removed)
    report = {
        "nemo_curator_version": scored["version"],
        "executor": "XennaExecutor (CPU)",
        "pipeline_seconds": scored["seconds"],
        "input_chunks": len(chunks),
        "kept": len(kept),
        "removed": len(removed),
        "filters": scored["filters"],
    }
    (out_dir / REPORT_NAME).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def compare_with_ours(chunks_path, curated_path, out_path, engine=None) -> None:
    """The side-by-side with our quality stage (the dashboard's NeMo comparison), written to `out_path`."""
    engine = engine or importlib.import_module("pipeline.nemo_compare")
    engine.main(chunks_path, curated_path, out_path)
