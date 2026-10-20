"""bfsi-curate: run the curation pipeline from the terminal.

    bfsi-curate run PDF_DIR -o OUT_DIR [--device auto|cpu|cuda]
    python -m pipeline.cli run PDF_DIR -o OUT_DIR        (same thing, without installing)

Exit code 0 on success, 2 for a bad input folder, 1 if the pipeline stopped.
"""
import argparse
import sys

from pipeline.api import curate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bfsi-curate", description="Curate regulatory PDFs into fine-tuning JSONL.")
    commands = parser.add_subparsers(dest="command", required=True)
    run_cmd = commands.add_parser("run", help="run every stage on a folder of PDFs")
    run_cmd.add_argument("pdf_dir", help="folder containing the .pdf files")
    run_cmd.add_argument("-o", "--output", required=True, help="folder for curated.jsonl and pipeline_summary.json")
    run_cmd.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto", help="default: auto-detect")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = curate(args.pdf_dir, args.output, args.device)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"{'stage':<16}{'in':>8}{'out':>8}{'removed':>9}")
    for stage in result.summary["stages"]:
        print(f"{stage['stage']:<16}{stage['docs_in']:>8}{stage['docs_out']:>8}{stage['removed']:>9}")
    print(f"\ndevice: {result.device}")
    print(f"chunks written: {result.summary['final_output_chunks']}")
    print(f"PII entities redacted: {result.summary['pii_entities_redacted']}")
    print(f"output: {result.output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
