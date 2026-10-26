"""Token statistics generator for curated BFSI regulatory datasets.

Reads curated JSONL records and computes token counts grouped per source document
and total corpus counts using an available tokenizer hierarchy (tiktoken cl100k_base,
locally cached HF tokenizer, or whitespace words).
"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union


def resolve_tokenizer(preference: str = "auto") -> Tuple[str, Callable[[str], int]]:
    """Resolve the tokenizer function based on availability and explicit preference.

    Hierarchy:
    1. tiktoken 'cl100k_base' labeled 'tiktoken:cl100k_base'
    2. Locally cached Hugging Face tokenizer (local_files_only=True, never silent network downloads)
    3. Whitespace words (explicitly labeled 'words')
    """
    pref = preference.lower().strip()

    if pref in ("words", "whitespace"):
        return "words", lambda text: len(text.split())

    if pref in ("auto", "tiktoken", "cl100k_base", "tiktoken:cl100k_base"):
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            return "tiktoken:cl100k_base", lambda text: len(enc.encode(text, disallowed_special=()))
        except Exception:
            if pref in ("tiktoken", "cl100k_base", "tiktoken:cl100k_base"):
                raise RuntimeError("tiktoken 'cl100k_base' requested but unavailable.")

    # Try locally cached transformers tokenizer without network requests
    if pref == "auto":
        try:
            from transformers import AutoTokenizer
            for candidate in ("gpt2", "meta-llama/Llama-2-7b", "nvidia/quality-classifier-deberta"):
                try:
                    tok = AutoTokenizer.from_pretrained(candidate, local_files_only=True)
                    return f"hf:{candidate}", lambda text: len(tok.tokenize(text))
                except Exception:
                    continue
        except Exception:
            pass

    # Final fallback: whitespace words
    return "words", lambda text: len(text.split())


def compute_token_stats(
    source: Union[str, Path, Iterable[Union[str, Dict[str, Any]]]],
    tokenizer: str = "auto",
) -> Dict[str, Any]:
    """Calculate token statistics per source file and across the dataset.

    Args:
        source: File path to a curated JSONL file, or an iterable of JSON lines or dicts.
        tokenizer: Preferred tokenizer name ('auto', 'tiktoken:cl100k_base', or 'words').

    Returns:
        Dict conforming to the contract:
        {
            "tokenizer": str,
            "total_tokens": int,
            "per_document": [
                {"source_file": str, "chunks": int, "tokens": int}
            ]
        }

    Raises:
        ValueError: If a line contains malformed JSON or lacks required fields (text, metadata.source_file),
                    specifying the input line number.
    """
    tok_name, count_fn = resolve_tokenizer(tokenizer)

    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(f"Curated JSONL not found: {path}")
        with path.open("r", encoding="utf-8") as f:
            items = list(f)
    else:
        items = list(source)

    chunks_per_doc: Dict[str, int] = {}
    tokens_per_doc: Dict[str, int] = {}

    for idx, item in enumerate(items):
        line_num = idx + 1
        record: Optional[Dict[str, Any]] = None

        if isinstance(item, str):
            line = item.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except Exception as exc:
                raise ValueError(f"Line {line_num}: malformed JSON ({exc})") from exc
            if not isinstance(parsed, dict):
                raise ValueError(f"Line {line_num}: record is not a JSON object")
            record = parsed
        elif isinstance(item, dict):
            record = item
        else:
            raise ValueError(f"Line {line_num}: unexpected item type {type(item).__name__}")

        text = record.get("text")
        if text is None or not isinstance(text, str):
            raise ValueError(f"Line {line_num}: record missing required 'text' string")

        metadata = record.get("metadata")
        if metadata is None or not isinstance(metadata, dict):
            raise ValueError(f"Line {line_num}: record missing required 'metadata' object")

        source_file = metadata.get("source_file")
        if not source_file or not isinstance(source_file, str):
            raise ValueError(f"Line {line_num}: metadata missing required 'source_file' string")

        tok_count = count_fn(text)
        chunks_per_doc[source_file] = chunks_per_doc.get(source_file, 0) + 1
        tokens_per_doc[source_file] = tokens_per_doc.get(source_file, 0) + tok_count

    per_document: List[Dict[str, Any]] = []
    for doc in sorted(chunks_per_doc.keys()):
        per_document.append({
            "source_file": doc,
            "chunks": chunks_per_doc[doc],
            "tokens": tokens_per_doc[doc],
        })

    total_tokens = sum(d["tokens"] for d in per_document)

    return {
        "tokenizer": tok_name,
        "total_tokens": total_tokens,
        "per_document": per_document,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate token statistics for curated JSONL dataset.")
    parser.add_argument("input", nargs="?", default=None, help="Input path to curated.jsonl")
    parser.add_argument("-i", "--input-path", dest="input_flag", default=None, help="Input path to curated.jsonl")
    parser.add_argument("-o", "--output", default=None, help="Output path for token_stats.json")
    parser.add_argument(
        "--tokenizer",
        default="auto",
        choices=["auto", "tiktoken", "cl100k_base", "tiktoken:cl100k_base", "words"],
        help="Tokenizer to use (default: auto)",
    )

    args = parser.parse_args(argv)
    input_path = args.input_flag or args.input

    if not input_path:
        repo_curated = Path(__file__).resolve().parent.parent / "data" / "output" / "curated.jsonl"
        dashboard_curated = Path(__file__).resolve().parent.parent / "dashboard" / "public" / "curated.jsonl"
        if repo_curated.is_file():
            input_path = str(repo_curated)
        elif dashboard_curated.is_file():
            input_path = str(dashboard_curated)
        else:
            parser.error("No input curated.jsonl file specified.")

    stats = compute_token_stats(input_path, tokenizer=args.tokenizer)
    output_json = json.dumps(stats, indent=2, ensure_ascii=False)

    if args.output:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write: write to temp file in same directory, flush & fsync, then replace
        temp_file = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=out_path.parent,
            prefix=f".{out_path.name}.tmp_",
            delete=False,
        )
        try:
            temp_file.write(output_json + "\n")
            temp_file.flush()
            os.fsync(temp_file.fileno())
            temp_file.close()
            os.replace(temp_file.name, out_path)
        except Exception:
            try:
                os.unlink(temp_file.name)
            except OSError:
                pass
            raise

        print(
            f"Wrote token stats to {out_path}: {len(stats['per_document'])} documents, "
            f"{stats['total_tokens']:,} total tokens ({stats['tokenizer']})"
        )
    else:
        print(output_json)

    return 0


if __name__ == "__main__":
    sys.exit(main())
