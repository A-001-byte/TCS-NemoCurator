"""Build docs/FINAL_NUMBERS.md from the dashboard's snapshot files.

    python scripts/make_final_numbers.py [--snapshots dashboard/public] [--out docs/FINAL_NUMBERS.md]

Every number comes from a snapshot file, nothing is typed in, so the slides, the README and the
dashboard cannot disagree. The optional snapshots (tokens, document types, NeMo comparison) are
reported as "not available" when their file is missing. The output is deterministic.
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SNAPSHOTS = ROOT / "dashboard" / "public"
DEFAULT_OUT = ROOT / "docs" / "FINAL_NUMBERS.md"


def load(snapshots: Path, name: str):
    """The parsed snapshot, or None if the file is absent. A byte-order mark is ignored."""
    path = snapshots / name
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8").lstrip("﻿"))


def n(value) -> str:
    return f"{value:,}" if isinstance(value, int) else "n/a"


def pct(part, whole) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "n/a"


def share(value) -> str:
    return f"{100 * value:.1f}%" if isinstance(value, (int, float)) else "n/a"


def table(header: list, rows: list) -> list:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    return lines + ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]


def stage(summary: dict, name: str) -> dict:
    return next((s for s in summary["stages"] if s["stage"] == name), {})


def corpus_section(summary: dict) -> list:
    extract = stage(summary, "extract")
    quality = stage(summary, "quality_filter")
    return ["## Corpus", ""] + table(
        ["Measure", "Value"],
        [
            ["Source PDFs", n(extract.get("docs_in"))],
            ["Readable (text layer)", n(extract.get("docs_out"))],
            ["Failed extraction", n(extract.get("removed"))],
            ["Final curated chunks", n(summary["final_output_chunks"])],
            ["Final characters", n(summary.get("final_output_chars"))],
            ["Compute device (quality stage)", quality.get("device", "not reported")],
        ],
    )


def stages_section(summary: dict) -> list:
    rows = []
    for record in summary["stages"]:
        reasons = ", ".join(
            f"{k} {n(v)}" for k, v in sorted(record.get("reason_counts", {}).items(), key=lambda kv: -kv[1])
        )
        rows.append(
            [record["stage"], n(record["docs_in"]), n(record["docs_out"]), n(record["removed"]), reasons or "none"]
        )
    return ["## Stages", ""] + table(["Stage", "In", "Out", "Removed", "Reasons"], rows)


def tags_section(summary: dict) -> list:
    tagged, untagged = summary["regulatory_tagged_count"], summary["regulatory_untagged_count"]
    return ["## Regulatory tags", ""] + table(
        ["Measure", "Value"],
        [
            ["Tagged (2 or more distinct regulatory keywords)", f"{n(tagged)} ({pct(tagged, tagged + untagged)})"],
            ["Untagged", n(untagged)],
            ["High regulatory density", n(summary["high_density_count"])],
        ],
    )


def pii_section(summary: dict) -> list:
    counts = summary["pii_entity_type_counts"]
    names = "on" if summary.get("name_detection_available") else "OFF (person names are not detected on this run)"
    lines = [
        "## PII redaction",
        "",
        f"- Entities redacted: {n(summary['pii_entities_redacted'])}",
        f"- Chunks with PII: {n(stage(summary, 'pii_redact').get('chunks_with_pii'))}",
        f"- Name detection: {names}",
        "",
    ]
    return lines + table(
        ["Type", "Count"], [[kind, n(count)] for kind, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    )


def doctypes_section(report) -> list:
    if not report:
        return ["## Document types", "", "Not available (doctype_eval.json is missing)."]
    return (
        ["## Document types", "", report["caption"], ""]
        + table(
            ["Measure", "Value"],
            [
                ["Documents scored", f"{n(report['n_scored'])} of {n(report['n_documents'])}"],
                ["Right, whole near-copy family held out", share(report["accuracy"]["by_family"])],
                ["Always guessing the biggest type", share(report["majority_baseline"])],
                ["Right, only the document held out (optimistic)", share(report["accuracy"]["by_document"])],
                [
                    "Confident answers",
                    f"{n(report['confident']['count'])} ({share(report['confident']['accuracy'])} right)",
                ],
                [
                    "Flagged low confidence",
                    f"{n(report['flagged']['count'])} ({share(report['flagged']['accuracy'])} right)",
                ],
            ],
        )
        + ["", report.get("variants_note", "")]
    )


def tokens_section(report) -> list:
    if not report:
        return ["## Tokens", "", "Not available (token_stats.json is missing)."]
    chunks = sum(d["chunks"] for d in report["per_document"])
    unit = "words" if "word" in report["tokenizer"].lower() else "tokens"
    return ["## Tokens", ""] + table(
        ["Measure", "Value"],
        [
            [f"Total {unit}", n(report["total_tokens"])],
            ["Counted with", report["tokenizer"]],
            ["Documents", n(len(report["per_document"]))],
            [f"{unit.capitalize()} per chunk", n(round(report["total_tokens"] / chunks)) if chunks else "n/a"],
        ],
    )


def nemo_section(report) -> list:
    if not report:
        return ["## NVIDIA NeMo Curator comparison", "", "Not available (nemo_comparison.json is missing)."]
    total = report["input_chunks"]
    overlap = report["overlap"]
    return [
        "## NVIDIA NeMo Curator comparison",
        "",
        f"NeMo Curator {report['nemo_curator_version']}, {report['executor']}, "
        f"on the {n(total)} chunks that enter our quality stage.",
        "",
    ] + table(
        ["Measure", "Value"],
        [
            [
                "Removed by NeMo's default filters",
                f"{n(report['nemo']['removed'])} ({pct(report['nemo']['removed'], total)})",
            ],
            [
                "Removed by our quality stage",
                f"{n(report['ours']['removed'])} ({pct(report['ours']['removed'], total)})",
            ],
            ["Removed by both", n(overlap["removed_by_both"])],
            ["Removed only by NeMo", n(overlap["only_nemo"])],
            ["Removed only by ours", n(overlap["only_ours"])],
            ["NeMo pipeline time", f"{report['pipeline_seconds']} s"],
        ],
    )


def build(snapshots: Path = DEFAULT_SNAPSHOTS) -> str:
    summary = load(snapshots, "pipeline_summary.json")
    if summary is None:
        raise FileNotFoundError(f"pipeline_summary.json not found in {snapshots}")
    blocks = [
        [
            "# Final numbers",
            "",
            "Generated by `scripts/make_final_numbers.py` from the dashboard snapshots in `dashboard/public/`. "
            "Do not edit by hand: refresh the snapshots, then run the script again.",
        ],
        corpus_section(summary),
        stages_section(summary),
        tags_section(summary),
        pii_section(summary),
        tokens_section(load(snapshots, "token_stats.json")),
        doctypes_section(load(snapshots, "doctype_eval.json")),
        nemo_section(load(snapshots, "nemo_comparison.json")),
    ]
    return "\n\n".join("\n".join(block) for block in blocks) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--snapshots", type=Path, default=DEFAULT_SNAPSHOTS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    args.out.write_text(build(args.snapshots), encoding="utf-8", newline="\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
