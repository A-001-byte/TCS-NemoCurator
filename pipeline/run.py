"""Orchestrator: runs the full curation pipeline end to end (T0.3).

Stage order is fixed: extract -> clean/langid -> dedup -> quality filter ->
PII redact -> output. PII redact runs AFTER dedup, never before (dedup relies
on stable content hashes; redacting first corrupts them).

Writes data/output/pipeline_summary.json, the single file the React dashboard reads.
"""
import json
import sys
from pathlib import Path

from pipeline import clean, dedup, extract, output, pii, quality

ROOT = Path(__file__).resolve().parent.parent
SUMMARY_PATH = ROOT / "data" / "output" / "pipeline_summary.json"

STAGES = [
    ("extract", extract.main),
    ("clean_langid", clean.main),
    ("dedup", dedup.main),
    ("quality_filter", quality.main),
    ("pii_redact", pii.main),
    ("output", output.main),
]

STAGE_RECORD_PATHS = {
    "extract": ROOT / "data" / "extracted" / "_stage_record.json",
    "clean_langid": ROOT / "data" / "cleaned" / "_stage_record.json",
    "dedup": ROOT / "data" / "deduped" / "_stage_record.json",
    "quality_filter": ROOT / "data" / "filtered" / "_stage_record.json",
    "pii_redact": ROOT / "data" / "redacted" / "_stage_record.json",
    "output": ROOT / "data" / "output" / "_stage_record.json",
}


def main():
    stage_results = []
    for name, fn in STAGES:
        try:
            fn()
        except SystemExit as exc:
            if exc.code not in (0, None):
                print(f"Pipeline stopped: stage '{name}' failed (exit {exc.code})")
                sys.exit(exc.code)
        record_path = STAGE_RECORD_PATHS[name]
        if record_path.exists():
            stage_results.append(json.loads(record_path.read_text(encoding="utf-8")))

    pii_examples_path = ROOT / "data" / "redacted" / "pii_examples.json"
    pii_examples = []
    if pii_examples_path.exists():
        pii_examples = json.loads(pii_examples_path.read_text(encoding="utf-8"))

    pii_stage = next((s for s in stage_results if s["stage"] == "pii_redact"), {})
    dedup_stage = next((s for s in stage_results if s["stage"] == "dedup"), {})
    output_stage = next((s for s in stage_results if s["stage"] == "output"), {})

    summary = {
        "stages": stage_results,
        "duplicates_removed": dedup_stage.get("removed", 0),
        "pii_entities_redacted": pii_stage.get("pii_entities_redacted", 0),
        "pii_entity_type_counts": pii_stage.get("entity_type_counts", {}),
        "name_detection_available": pii_stage.get("name_detection_available", False),
        "pii_examples": pii_examples,
        "final_output_chunks": output_stage.get("docs_out", 0),
        "final_output_chars": output_stage.get("total_chars", 0),
    }
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    summary_json = json.dumps(summary, indent=2, ensure_ascii=False)
    SUMMARY_PATH.write_text(summary_json, encoding="utf-8")

    dashboard_public = ROOT / "dashboard" / "public"
    if dashboard_public.is_dir():
        (dashboard_public / "pipeline_summary.json").write_text(summary_json, encoding="utf-8")

    print(f"\nPipeline complete. Summary written to {SUMMARY_PATH}")
    print(f"duplicates_removed={summary['duplicates_removed']}")
    print(f"pii_entities_redacted={summary['pii_entities_redacted']}")


if __name__ == "__main__":
    main()
