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
import os
import shutil
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from pipeline import clean, dedup, extract, heal, output, pii, quality, run

DATA_DIR = run.ROOT / "data"
STAGE_DIRS = ("raw", "extracted", "cleaned", "healed", "deduped", "filtered", "redacted", "output")
MODULES = (extract, clean, heal, dedup, quality, pii, output, run)
DEVICE_ENV = "CURATOR_DEVICE"

# ponytail: one run at a time, because runs patch module globals; a job queue if this ever serves more than one user.
RUN_LOCK = threading.Lock()


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


def run_isolated(files=(), raw_dir=None, output_dir=None):
    """Run every stage in a throwaway data/ folder.

    `files` is a list of (name, bytes) PDFs written into that folder; alternatively `raw_dir`
    points the extract stage straight at an existing folder of PDFs (nothing is copied).
    With `output_dir`, curated.jsonl and pipeline_summary.json are copied there before the
    throwaway folder is deleted. Returns ({"summary", "curated_jsonl"}, log), or (None, log)
    if a stage stopped the pipeline.
    """
    with RUN_LOCK, tempfile.TemporaryDirectory(prefix="kyc_run_") as tmp:
        tmp_root = Path(tmp)
        for sub in STAGE_DIRS:
            (tmp_root / "data" / sub).mkdir(parents=True)
        for name, data in files:
            (tmp_root / "data" / "raw" / name).write_bytes(data)

        log = io.StringIO()
        with _pipeline_rooted_at(tmp_root), contextlib.redirect_stdout(log):
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


def _resolve_device(requested: str) -> str:
    """'cpu' / 'cuda:0'. Uses pipeline.device once it exists; until then nothing runs on a GPU."""
    try:
        from pipeline.device import pick
    except ImportError:
        return "cpu" if requested == "auto" else requested
    return pick(requested)


def curate(input_dir, output_dir, device: str = "auto") -> CurateResult:
    """Run the full pipeline on every *.pdf in `input_dir`; write the results to `output_dir`."""
    input_dir, output_dir = Path(input_dir), Path(output_dir)
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Input folder not found: {input_dir}")
    if not any(input_dir.glob("*.pdf")):
        raise ValueError(f"No .pdf files in {input_dir}")

    resolved = _resolve_device(device)
    previous = os.environ.get(DEVICE_ENV)
    os.environ[DEVICE_ENV] = resolved
    try:
        result, log = run_isolated(raw_dir=input_dir, output_dir=output_dir)
    finally:
        if previous is None:
            os.environ.pop(DEVICE_ENV, None)
        else:
            os.environ[DEVICE_ENV] = previous
    if result is None:
        raise RuntimeError(f"The pipeline stopped before finishing.\n{log}")
    return CurateResult(
        result["summary"], output_dir / "curated.jsonl", output_dir / "pipeline_summary.json", resolved, log
    )
