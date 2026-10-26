
"""Refresh dashboard snapshots using the isolated NeMo curation API."""

import argparse
import json
import re
import shutil
import tempfile
from pathlib import Path

from pipeline.api import curate

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "data" / "raw"
DEFAULT_OUTPUT = ROOT / "dashboard" / "public"

# Defensive masking for common personal-data patterns.
EMAIL_RE = re.compile(
    r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"
)
AADHAAR_RE = re.compile(r"(?<!\d)(?:\d[ -]?){11}\d(?!\d)")
TEN_DIGIT_RE = re.compile(r"(?<!\d)\d{10}(?!\d)")

SAFE_EXAMPLE_KEYS = {
    "type", "entity_type", "detector", "rule", "label", "category"
}


def mask_text(value):
    """Mask common identifiers without changing other text."""
    value = AADHAAR_RE.sub("[AADHAAR REDACTED]", value)
    value = EMAIL_RE.sub("[EMAIL REDACTED]", value)
    value = TEN_DIGIT_RE.sub("[PHONE/ID REDACTED]", value)
    return value


def sanitize_tree(value):
    """Mask common identifiers in strings throughout a JSON structure."""
    if isinstance(value, dict):
        return {key: sanitize_tree(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_tree(item) for item in value]
    if isinstance(value, str):
        return mask_text(value)
    return value


def sanitize_examples(value):
    """Keep example structure and detector labels, but hide example values."""
    if isinstance(value, dict):
        safe = {}
        for key, item in value.items():
            if key.lower() in SAFE_EXAMPLE_KEYS and isinstance(item, str):
                safe[key] = item
            elif isinstance(item, str):
                safe[key] = "[REDACTED]"
            else:
                safe[key] = sanitize_examples(item)
        return safe
    if isinstance(value, list):
        return [sanitize_examples(item) for item in value]
    if isinstance(value, str):
        return "[REDACTED]"
    return value


def write_safe_jsonl(source, destination):
    """Write curated chunks with common identifiers defensively masked."""
    with source.open(encoding="utf-8") as reader:
        with destination.open("w", encoding="utf-8") as writer:
            for line in reader:
                if not line.strip():
                    continue
                record = json.loads(line)
                writer.write(
                    json.dumps(sanitize_tree(record), ensure_ascii=False) + "\n"
                )


def refresh(input_dir=DEFAULT_INPUT, output_dir=DEFAULT_OUTPUT):
    """Run curation in isolation and publish safe dashboard snapshots."""
    input_dir = Path(input_dir).resolve()
    output_dir = Path(output_dir).resolve()

    if not input_dir.is_dir():
        raise FileNotFoundError(f"Input folder not found: {input_dir}")
    if not any(input_dir.glob("*.pdf")):
        raise ValueError(f"No PDF files found in {input_dir}")

    # Temporary output keeps intermediate results outside the project data folder.
    with tempfile.TemporaryDirectory(prefix="dashboard_refresh_") as temp:
        temp_output = Path(temp) / "output"
        result = curate(input_dir, temp_output, device="auto")

        summary = sanitize_tree(result.summary)
        summary["pii_examples"] = sanitize_examples(
            result.summary.get("pii_examples", [])
        )

        # Publish only after the pipeline completes successfully.
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_summary = output_dir / "pipeline_summary.json"
        safe_curated = output_dir / "curated.jsonl"
        temp_summary = output_dir / ".pipeline_summary.json.tmp"
        temp_curated = output_dir / ".curated.jsonl.tmp"

        try:
            temp_summary.write_text(
                json.dumps(summary, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            write_safe_jsonl(result.output_path, temp_curated)
            temp_summary.replace(safe_summary)
            temp_curated.replace(safe_curated)
        finally:
            temp_summary.unlink(missing_ok=True)
            temp_curated.unlink(missing_ok=True)

    print("Dashboard snapshots refreshed successfully.")
    print(f"Readable documents: {len(summary.get('documents', []))}")
    print(f"Final chunks: {summary.get('final_output_chunks', 0)}")
    print(f"PII entities redacted: {summary.get('pii_entities_redacted', 0)}")
    print(f"Device selected: {result.device}")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    refresh(args.input_dir, args.output_dir)


if __name__ == "__main__":
    main()
