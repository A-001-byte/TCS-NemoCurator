"""Refresh the dashboard snapshots from a real pipeline run.

    python -m pipeline.refresh_snapshots [--input-dir data/raw] [--output-dir dashboard/public]

The run happens in a temporary folder (pipeline.api.curate), so the repository's data/ is untouched.
Nothing is published unless the run finishes, and nothing is published that still contains personal
data the pipeline itself would redact. The published curated.jsonl is the pipeline's output byte for
byte; only the PII examples, which show original values by design, are masked.
"""

import argparse
import json
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path

from pipeline import pii
from pipeline.api import curate

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "data" / "raw"
DEFAULT_OUTPUT = ROOT / "dashboard" / "public"
REFRESH_DEVICE_ENV = "CURATOR_REFRESH_DEVICE"
REFRESH_QUALITY_SIGNAL_ENV = "CURATOR_REFRESH_QUALITY_SIGNAL"

VISIBLE_CHARS = 2  # most characters of an original value left readable in a published example
MAX_LEAKS_REPORTED = 5
_ABSOLUTE_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|/)")


def _mask_text(text: str) -> str:
    """Keep the first letters or digits (at most VISIBLE_CHARS, and never more than a third of the
    value, so a very short value is hidden completely), star the rest, keep every separator."""
    visible = min(VISIBLE_CHARS, sum(char.isalnum() for char in text) // 3)
    shown = 0
    masked = []
    for char in text:
        if char.isalnum():
            masked.append(char if shown < visible else "*")
            shown += 1
        else:
            masked.append(char)
    return "".join(masked)


def mask_value(entity_type: str, value: str) -> str:
    """Partly hide an original PII value. An email keeps its domain, which names an organisation."""
    if entity_type == "EMAIL" and "@" in value:
        local, domain = value.split("@", 1)
        return f"{_mask_text(local)}@{domain}"
    return _mask_text(value)


def find_residual_pii(text: str) -> dict:
    """Entity counts the pipeline's own redactor would still replace in `text` (empty = clean)."""
    counts: dict = {}
    pii.redact_regex(text, counts, [], "residual-check", {})
    return counts


def _redact_context(text: str) -> str:
    """Redact personal data in the text around an example (a neighbour's value may not have been
    replaced yet when the example was recorded)."""
    return pii.redact_regex(text, {}, [], "context", {})


def mask_example(example: dict) -> dict:
    """A PII example safe to publish: same document and type, original value partly hidden, and the
    surrounding text redacted."""
    masked = dict(example)
    masked["before"] = mask_value(str(example.get("entity_type", "")), str(example.get("before", "")))
    for key in ("context_before", "context_after"):
        masked[key] = _redact_context(str(example.get(key, "")))
    return masked


def without_local_paths(value):
    """Replace any absolute file path in a JSON structure by its file name (no usernames or folders
    of the machine that produced it)."""
    if isinstance(value, dict):
        return {key: without_local_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [without_local_paths(item) for item in value]
    if isinstance(value, str) and _ABSOLUTE_PATH_RE.match(value):
        return re.split(r"[\\/]", value)[-1]
    return value


def check_curated_is_clean(curated_path: Path) -> None:
    """Raise ValueError if the curated output still holds data the pipeline would redact."""
    leaks = []
    for number, line in enumerate(curated_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        found = find_residual_pii(json.loads(line)["text"])
        if found:
            leaks.append(f"line {number}: {found}")
            if len(leaks) >= MAX_LEAKS_REPORTED:
                break
    if leaks:
        raise ValueError("Curated output still contains personal data, nothing was published: " + "; ".join(leaks))


def publish_snapshots(summary: dict, curated_path: Path, output_dir: Path) -> dict:
    """Write pipeline_summary.json and curated.jsonl into `output_dir` (all or nothing)."""
    check_curated_is_clean(curated_path)
    published = without_local_paths(summary)
    published["pii_examples"] = [mask_example(example) for example in summary.get("pii_examples", [])]

    output_dir.mkdir(parents=True, exist_ok=True)
    pending = {
        output_dir / "pipeline_summary.json": output_dir / ".pipeline_summary.json.tmp",
        output_dir / "curated.jsonl": output_dir / ".curated.jsonl.tmp",
    }
    try:
        (output_dir / ".pipeline_summary.json.tmp").write_text(
            json.dumps(published, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        shutil.copyfile(curated_path, output_dir / ".curated.jsonl.tmp")
        for final, temporary in pending.items():
            temporary.replace(final)
    finally:
        for temporary in pending.values():
            temporary.unlink(missing_ok=True)
    return published


def refresh(input_dir=DEFAULT_INPUT, output_dir=DEFAULT_OUTPUT) -> dict:
    """Run the pipeline on `input_dir` and publish the snapshots into `output_dir`."""
    input_dir = Path(input_dir).resolve()
    output_dir = Path(output_dir).resolve()
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Input folder not found: {input_dir}")
    if not any(input_dir.glob("*.pdf")):
        raise ValueError(f"No PDF files found in {input_dir}")

    device = os.environ.get(REFRESH_DEVICE_ENV, "auto").strip().lower()
    quality_signal = os.environ.get(REFRESH_QUALITY_SIGNAL_ENV, "off").strip().lower()
    if device not in ("auto", "cpu", "cuda"):
        raise ValueError(f"{REFRESH_DEVICE_ENV} must be auto, cpu or cuda")
    if quality_signal not in ("off", "model"):
        raise ValueError(f"{REFRESH_QUALITY_SIGNAL_ENV} must be off or model")

    with tempfile.TemporaryDirectory(prefix="dashboard_refresh_") as temp:
        result = curate(
            input_dir,
            Path(temp) / "output",
            device=device,
            pii_engine="regex",
            quality_signal=quality_signal,
        )
        published = publish_snapshots(result.summary, result.output_path, output_dir)

    log.info(
        "Snapshots refreshed: %d documents, %d chunks, %d PII entities, device %s",
        len(published.get("documents", [])),
        published.get("final_output_chunks", 0),
        published.get("pii_entities_redacted", 0),
        result.device,
    )
    return published


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    refresh(args.input_dir, args.output_dir)


if __name__ == "__main__":
    main()
