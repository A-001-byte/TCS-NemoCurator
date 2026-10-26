"""bfsi-curate: run the curation pipeline from the terminal.

    bfsi-curate run PDF_DIR -o OUT_DIR [--device auto|cpu|cuda] [--verbose]
    bfsi-curate serve [--host 127.0.0.1] [--port 8000]       the local API for the dashboard
    bfsi-curate --version
    python -m pipeline.cli ...                                same thing, without installing

Exit codes: 0 success; 1 the pipeline stopped (the reason is printed; --verbose adds its log);
2 a bad input folder or bad arguments; 130 interrupted with Ctrl+C.
"""
import argparse
import sys
from typing import Optional

from pipeline import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bfsi-curate", description="Curate regulatory PDFs into fine-tuning JSONL.")
    parser.add_argument("--version", action="version", version=f"bfsi-curate {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    run_cmd = commands.add_parser("run", help="run every stage on a folder of PDFs")
    run_cmd.add_argument("pdf_dir", help="folder containing the .pdf files")
    run_cmd.add_argument("-o", "--output", required=True, help="folder for curated.jsonl and pipeline_summary.json")
    run_cmd.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto", help="default: auto-detect")
    run_cmd.add_argument("-v", "--verbose", action="store_true", help="on failure, print the pipeline's full log")

    serve_cmd = commands.add_parser("serve", help="start the local API the dashboard talks to")
    serve_cmd.add_argument("--host", help="default 127.0.0.1 (or CURATOR_HOST)")
    serve_cmd.add_argument("--port", type=int, help="default 8000 (or CURATOR_PORT)")
    return parser


def _run(args) -> int:
    from pipeline.api import curate  # imported late: --help and --version stay instant

    try:
        result = curate(args.pdf_dir, args.output, args.device)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        reason, _, pipeline_log = str(exc).partition("\n")
        print(f"error: {reason}", file=sys.stderr)
        if args.verbose and pipeline_log:
            print(pipeline_log, file=sys.stderr)
        return 1

    print(f"{'stage':<16}{'in':>8}{'out':>8}{'removed':>9}")
    for stage in result.summary["stages"]:
        print(f"{stage['stage']:<16}{stage['docs_in']:>8}{stage['docs_out']:>8}{stage['removed']:>9}")
    print(f"\ndevice: {result.device}")
    print(f"chunks written: {result.summary['final_output_chunks']}")
    print(f"PII entities redacted: {result.summary['pii_entities_redacted']}")
    print(f"output: {result.output_path}")
    if not result.summary.get("name_detection_available", True):
        print("warning: person-name detection is OFF (the spaCy model did not load), so names are not redacted.", file=sys.stderr)
    return 0


def _serve(args) -> int:
    from pipeline.server import main as serve_main

    flags = []
    if args.host:
        flags += ["--host", args.host]
    if args.port is not None:
        flags += ["--port", str(args.port)]
    return serve_main(flags)


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _serve(args) if args.command == "serve" else _run(args)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
