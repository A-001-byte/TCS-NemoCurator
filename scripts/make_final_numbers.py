"""Build docs/FINAL_NUMBERS.md from the dashboard's snapshot files.

    python scripts/make_final_numbers.py [--snapshots dashboard/public] [--out docs/FINAL_NUMBERS.md]
                                         [--readme README.md] [--check]

It also rewrites the headline table in README.md, between the two `numbers:` marker comments.
`--check` writes nothing and exits 1 if either file is out of date. Every number comes from a snapshot file, nothing is typed in, so the slides, the README and the
dashboard cannot disagree. The optional snapshots (tokens, document types, NeMo comparison) are
reported as "not available" when their file is missing. The output is deterministic.
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SNAPSHOTS = ROOT / "dashboard" / "public"
DEFAULT_OUT = ROOT / "docs" / "FINAL_NUMBERS.md"
DEFAULT_README = ROOT / "README.md"


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


README_START = "<!-- numbers:start (generated by scripts/make_final_numbers.py, do not edit by hand) -->"
README_END = "<!-- numbers:end -->"


def readme_block(snapshots: Path = DEFAULT_SNAPSHOTS) -> str:
    """The README's headline table: the same numbers as FINAL_NUMBERS.md, in a handful of rows."""
    summary = load(snapshots, "pipeline_summary.json")
    if summary is None:
        raise FileNotFoundError(f"pipeline_summary.json not found in {snapshots}")
    extract, quality = stage(summary, "extract"), stage(summary, "quality_filter")
    tagged, untagged = summary["regulatory_tagged_count"], summary["regulatory_untagged_count"]
    names = "name detection on" if summary.get("name_detection_available") else "name detection OFF"
    rows = [
        ["PDFs in / readable", f"{n(extract.get('docs_in'))} / {n(extract.get('docs_out'))}"],
        [
            "Final curated chunks",
            f"{n(summary['final_output_chunks'])} ({n(summary.get('final_output_chars'))} characters)",
        ],
        [
            "Removed by dedup / by the quality filter",
            f"{n(stage(summary, 'dedup').get('removed'))} / {n(quality.get('removed'))}",
        ],
        ["Tagged as regulatory (2 or more keywords)", f"{n(tagged)} ({pct(tagged, tagged + untagged)})"],
        ["Personal-data items hidden", f"{n(summary['pii_entities_redacted'])} ({names})"],
    ]
    tokens = load(snapshots, "token_stats.json")
    if tokens:
        unit = "words" if "word" in tokens["tokenizer"].lower() else "tokens"
        rows.append([f"Training text ({tokens['tokenizer']})", f"{n(tokens['total_tokens'])} {unit}"])
    doctypes = load(snapshots, "doctype_eval.json")
    if doctypes:
        rows.append(
            [
                "Document type found, whole near-copy family held out",
                f"{share(doctypes['accuracy']['by_family'])} (guessing the biggest type: {share(doctypes['majority_baseline'])})",
            ]
        )
    nemo = load(snapshots, "nemo_comparison.json")
    if nemo:
        total = nemo["input_chunks"]
        rows.append(
            [
                f"Removed on the same {n(total)} chunks: NeMo Curator {nemo['nemo_curator_version'].split('+')[0]} / ours",
                f"{n(nemo['nemo']['removed'])} ({pct(nemo['nemo']['removed'], total)}) / "
                f"{n(nemo['ours']['removed'])} ({pct(nemo['ours']['removed'], total)})",
            ]
        )
    rows.append(["Compute device (quality stage)", quality.get("device", "not reported")])
    return "\n".join(table(["Measure", "Result"], rows))


def update_readme(text: str, block: str) -> str:
    """`text` with the region between the two markers replaced by `block`. Raises ValueError without markers."""
    start, end = text.find(README_START), text.find(README_END)
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"README needs the two marker lines:\n{README_START}\n{README_END}")
    return text[: start + len(README_START)] + "\n\n" + block + "\n\n" + text[end:]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--snapshots", type=Path, default=DEFAULT_SNAPSHOTS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--readme", type=Path, default=DEFAULT_README)
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 if a generated file is out of date")
    args = parser.parse_args(argv)

    final_numbers = build(args.snapshots)
    readme = update_readme(args.readme.read_text(encoding="utf-8"), readme_block(args.snapshots))
    targets = {args.out: final_numbers, args.readme: readme}
    if args.check:
        stale = [
            str(path)
            for path, text in targets.items()
            if not path.is_file() or path.read_text(encoding="utf-8") != text
        ]
        if stale:
            print("out of date (run python scripts/make_final_numbers.py): " + ", ".join(stale))
            return 1
        print("generated documents are up to date")
        return 0
    for path, text in targets.items():
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
