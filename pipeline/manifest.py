"""A record of each run: `manifest.json` (what ran, on which inputs, producing which outputs) and `audit.jsonl`
(an append-only log of who started and finished or failed a run).

Both are written next to `curated.jsonl` by `pipeline.api.curate`, so the library and the command line leave the same
trail. `curated.jsonl` and `pipeline_summary.json` are untouched by this: the manifest only describes them. File
names and hashes are recorded, never folder paths, so a manifest can be shared without leaking where the data lived.
"""

import getpass
import hashlib
import json
import platform
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from pipeline import __version__

MANIFEST_VERSION = 1
MANIFEST_NAME = "manifest.json"
AUDIT_NAME = "audit.jsonl"
READ_BLOCK = 1024 * 1024


def new_run_id() -> str:
    return uuid.uuid4().hex


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(READ_BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def _line_count(path: Path) -> int:
    with Path(path).open("rb") as handle:
        return sum(1 for line in handle if line.strip())


def describe_inputs(pdfs: Iterable[Path]) -> list:
    return [
        {"name": p.name, "bytes": p.stat().st_size, "sha256": file_sha256(p)}
        for p in sorted(pdfs, key=lambda p: p.name)
    ]


def _user() -> str:
    try:
        return getpass.getuser()
    except Exception:  # no passwd entry (some containers): say so rather than fail the run
        return "unknown"


def audit(output_dir: Path, event: str, run_id: str, **fields) -> None:
    """Append one line to audit.jsonl in `output_dir`, creating the folder if needed."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    record = {"time": _stamp(utc_now()), "event": event, "run_id": run_id, "user": _user(), **fields}
    with (output_dir / AUDIT_NAME).open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_manifest(
    output_dir: Path,
    *,
    run_id: str,
    started: datetime,
    finished: datetime,
    pdfs: Iterable[Path],
    summary: dict,
    device: str,
    pii_engine: str,
    quality_signal: str,
    curated_path: Path,
    summary_path: Path,
) -> Path:
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "tool": {
            "name": "bfsi-curate",
            "version": __version__,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "run": {
            "run_id": run_id,
            "started_at": _stamp(started),
            "finished_at": _stamp(finished),
            "duration_seconds": round((finished - started).total_seconds(), 1),
            "device": device,
            "pii_engine": pii_engine,
            "quality_signal": quality_signal,
            "name_detection_available": summary.get("name_detection_available", True),
        },
        "inputs": describe_inputs(pdfs),
        "stages": [
            {k: stage[k] for k in ("stage", "docs_in", "docs_out", "removed") if k in stage}
            for stage in summary.get("stages", [])
        ],
        "outputs": [
            {
                "name": Path(curated_path).name,
                "bytes": Path(curated_path).stat().st_size,
                "sha256": file_sha256(curated_path),
                "records": _line_count(curated_path),
            },
            {
                "name": Path(summary_path).name,
                "bytes": Path(summary_path).stat().st_size,
                "sha256": file_sha256(summary_path),
            },
        ],
    }
    path = Path(output_dir) / MANIFEST_NAME
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return path


def failure_reason(exc: BaseException) -> str:
    """The first line of the error: enough for the audit log without the pipeline's whole log."""
    return (str(exc).partition("\n")[0] or type(exc).__name__)[:300]
