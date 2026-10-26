"""The one entry point to the pipeline: the library, the CLI and the HTTP server all call this.

    from pipeline.api import curate
    result = curate("pdfs/", "out/")          # writes out/curated.jsonl and out/pipeline_summary.json
    print(result.summary["final_output_chunks"], result.device)

Every run happens in its own temporary data/ folder: each stage's module-level paths are rebased
there for the duration of the run, so the committed corpus under data/ is never touched.
"""

import contextlib
import io
import json
import logging
import os
import re
import shutil
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from pipeline import clean, dedup, extract, heal, output, pii, quality, run
from pipeline.device import pick

log = logging.getLogger(__name__)

DATA_DIR = run.ROOT / "data"
STAGE_DIRS = ("raw", "extracted", "cleaned", "healed", "deduped", "filtered", "redacted", "output")
MODULES = (extract, clean, heal, dedup, quality, pii, output, run)
DEVICE_ENV = "CURATOR_DEVICE"

# ponytail: one run at a time, because runs patch module globals; a job queue if this ever serves more than one user.
RUN_LOCK = threading.Lock()


class PipelineBusy(RuntimeError):
    """Another run holds the pipeline; try again when it has finished."""


_STOPPED_RE = re.compile(r"Pipeline stopped: stage '([^']+)' failed")


def stop_reason(pipeline_log: str) -> str:
    """One plain sentence on why the pipeline stopped, read from its log."""
    match = _STOPPED_RE.search(pipeline_log)
    stage = match.group(1) if match else None
    if stage == "extract":
        return "The pipeline stopped at the extract stage: no PDF yielded any text (scanned, empty or damaged files)."
    if stage:
        return f"The pipeline stopped at the {stage} stage."
    return "The pipeline stopped before finishing."


@contextlib.contextmanager
def _exclusive(wait: bool):
    """Hold the one-run-at-a-time lock; with wait=False raise PipelineBusy instead of queueing."""
    if not RUN_LOCK.acquire(blocking=wait):
        raise PipelineBusy("Another pipeline run is in progress; try again when it has finished.")
    try:
        yield
    finally:
        RUN_LOCK.release()


@dataclass(frozen=True)
class CurateResult:
    summary: dict
    output_path: Path
    summary_path: Path
    device: str
    log: str


def _rebase(value, new_data_dir):
    if isinstance(value, Path) and value.is_relative_to(DATA_DIR):
        return new_data_dir / value.relative_to(DATA_DIR)
    if isinstance(value, dict) and value and all(isinstance(v, Path) for v in value.values()):
        return {k: _rebase(v, new_data_dir) for k, v in value.items()}
    return value


@contextlib.contextmanager
def _pipeline_rooted_at(tmp_root: Path):
    originals = {mod: dict(vars(mod)) for mod in MODULES}
    try:
        for mod in MODULES:
            for name, value in originals[mod].items():
                if name.isupper():
                    setattr(mod, name, _rebase(value, tmp_root / "data"))
        run.ROOT = tmp_root
        yield
    finally:
        for mod in MODULES:
            for name, value in originals[mod].items():
                if name.isupper():
                    setattr(mod, name, value)


def run_isolated(
    files=(),
    raw_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    wait: bool = True,
    pii_engine: Optional[str] = None,
    quality_signal: Optional[str] = None,
    ocr: Optional[bool] = None,
) -> tuple:
    """Run every stage in a throwaway data/ folder.

    `files` is a list of (name, bytes) PDFs written into that folder; alternatively `raw_dir`
    points the extract stage straight at an existing folder of PDFs (nothing is copied).
    With `output_dir`, curated.jsonl and pipeline_summary.json are copied there before the
    throwaway folder is deleted. Returns ({"summary", "curated_jsonl"}, log), or (None, log)
    if a stage stopped the pipeline. Only one run happens at a time: with wait=False a second
    caller gets PipelineBusy at once instead of queueing behind a run that takes minutes.
    """
    if pii_engine not in (None, "regex", "gliner"):
        raise ValueError(f"Unknown PII engine: {pii_engine}")
    if quality_signal not in (None, "off", "cache", "model"):
        raise ValueError(f"Unknown quality signal mode: {quality_signal}")

    with _exclusive(wait), tempfile.TemporaryDirectory(prefix="kyc_run_") as tmp:
        tmp_root = Path(tmp)
        for sub in STAGE_DIRS:
            (tmp_root / "data" / sub).mkdir(parents=True)
        for name, data in files:
            (tmp_root / "data" / "raw" / name).write_bytes(data)

        log = io.StringIO()
        with _pipeline_rooted_at(tmp_root), contextlib.redirect_stdout(log):
            if pii_engine is not None:
                pii.USE_GLINER_PII = pii_engine == "gliner"
            if quality_signal is not None:
                quality.QUALITY_SIGNAL_MODE = quality_signal
                quality.QUALITY_SIGNAL_STRICT = quality_signal == "model"
            if ocr is not None:
                extract.OCR_ENABLED = ocr
            if raw_dir is not None:
                extract.RAW_DIR = Path(raw_dir)
            try:
                run.main()
            except SystemExit:
                return None, log.getvalue()
            curated_path, summary_path = output.OUT_PATH, run.SUMMARY_PATH
            result = {
                "summary": json.loads(summary_path.read_text(encoding="utf-8")),
                "curated_jsonl": curated_path.read_text(encoding="utf-8"),
            }
        if output_dir is not None:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(curated_path, Path(output_dir) / "curated.jsonl")
            shutil.copyfile(summary_path, Path(output_dir) / "pipeline_summary.json")
        return result, log.getvalue()


def curate(
    input_dir: Union[str, Path],
    output_dir: Union[str, Path],
    device: str = "auto",
    *,
    pii_engine: str = "regex",
    quality_signal: str = "off",
    ocr: bool = False,
) -> CurateResult:
    """Run the full pipeline on every PDF in `input_dir`; write the results to `output_dir`.

    Raises FileNotFoundError (no such folder), ValueError (no PDFs in it), PipelineBusy (another run
    holds the pipeline; it waits its turn instead, see run_isolated) or RuntimeError with a one-line
    reason first when a stage stops the pipeline (for example, no PDF could be read).
    """
    input_dir, output_dir = Path(input_dir), Path(output_dir)
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Input folder not found: {input_dir}")
    if not extract.list_pdfs(input_dir):
        raise ValueError(f"No .pdf files in {input_dir}")

    if ocr:
        reason = extract.ocr_unavailable_reason()
        if reason:
            raise RuntimeError(reason)
    resolved = pick(device)
    if device == "cuda" and resolved == "cpu":
        raise RuntimeError(
            "CUDA requested but CUDA-enabled PyTorch is unavailable in this Python environment. "
            "Install the CUDA PyTorch build and try again."
        )
    previous = os.environ.get(DEVICE_ENV)
    os.environ[DEVICE_ENV] = resolved
    try:
        result, pipeline_log = run_isolated(
            raw_dir=input_dir,
            output_dir=output_dir,
            pii_engine=pii_engine,
            quality_signal=quality_signal,
            ocr=ocr,
        )
    finally:
        if previous is None:
            os.environ.pop(DEVICE_ENV, None)
        else:
            os.environ[DEVICE_ENV] = previous
    if result is None:
        raise RuntimeError(f"{stop_reason(pipeline_log)}\n{pipeline_log}")
    summary = result["summary"]
    if not summary.get("name_detection_available", True):
        log.warning(
            "Person-name detection is OFF on this run: the spaCy model did not load, so names are not redacted."
        )
    return CurateResult(
        summary, output_dir / "curated.jsonl", output_dir / "pipeline_summary.json", resolved, pipeline_log
    )
