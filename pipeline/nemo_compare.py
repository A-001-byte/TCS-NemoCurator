"""Run real NVIDIA NeMo Curator heuristic filters on our post-dedup chunks and
compare with what our quality stage removed.

Needs nemo_curator installed (the Ubuntu VM / WSL setup in SETUP.md), so it is
not part of pipeline/run.py. Output is a snapshot the dashboard reads:

  python -m pipeline.nemo_compare DEDUPED_CHUNKS.jsonl CURATED.jsonl OUT.json

DEDUPED_CHUNKS = data/deduped/chunks.jsonl (input to our quality filter)
CURATED        = data/output/curated.jsonl (our final output; chunk_ids we kept)
"""
import json
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

import nemo_curator
from nemo_curator.backends.xenna.executor import XennaExecutor
from nemo_curator.pipeline.pipeline import Pipeline
from nemo_curator.stages.text.filters.heuristic.repetition.repetition import (
    RepeatingDuplicateNGramsFilter,
    RepeatingTopNGramsFilter,
)
from nemo_curator.stages.text.filters.heuristic.string import (
    BoilerPlateStringFilter,
    MeanWordLengthFilter,
    NonAlphaNumericFilter,
    NumbersFilter,
    SymbolsToWordsFilter,
    WordCountFilter,
    WordsWithoutAlphabetsFilter,
)
from nemo_curator.stages.text.filters.score_filter import ScoreFilter
from nemo_curator.stages.text.io.reader.jsonl import JsonlReader
from nemo_curator.stages.text.io.writer.jsonl import JsonlWriter

# NeMo defaults (Gopher-style thresholds); the last field names the quality.py
# reason that checks the same property, when there is one.
FILTERS = [
    ("word_count", "Word count (50–100k words)", WordCountFilter, {}, "too_few_words"),
    ("non_alpha_numeric", "Non-alphanumeric ratio ≤ 0.25", NonAlphaNumericFilter, {}, "low_alpha_ratio"),
    ("symbols_to_words", "Symbol-to-word ratio ≤ 0.1", SymbolsToWordsFilter, {}, "high_symbol_ratio"),
    ("numbers", "Digit ratio ≤ 0.15", NumbersFilter, {}, None),
    ("words_without_alphabets", "≥ 80% of words contain a letter", WordsWithoutAlphabetsFilter, {}, None),
    ("mean_word_length", "Mean word length 3–10", MeanWordLengthFilter, {}, None),
    ("top_2grams", "Top 2-gram share ≤ 0.20", RepeatingTopNGramsFilter, {"n": 2, "max_repeating_ngram_ratio": 0.20}, "low_lexical_diversity"),
    ("top_3grams", "Top 3-gram share ≤ 0.18", RepeatingTopNGramsFilter, {"n": 3, "max_repeating_ngram_ratio": 0.18}, "low_lexical_diversity"),
    ("top_4grams", "Top 4-gram share ≤ 0.16", RepeatingTopNGramsFilter, {"n": 4, "max_repeating_ngram_ratio": 0.16}, "low_lexical_diversity"),
    ("dup_5grams", "Duplicated 5-gram share ≤ 0.15", RepeatingDuplicateNGramsFilter, {"n": 5, "max_repeating_duplicate_ngram_ratio": 0.15}, "low_lexical_diversity"),
    ("boilerplate", "Boilerplate strings (terms of use, cookies…)", BoilerPlateStringFilter, {}, None),
]


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def run_nemo_pipeline(input_path, filters):
    """The same filter chain through NeMo's own Pipeline + executor, end to end."""
    out_dir = Path(tempfile.mkdtemp(prefix="nemo_compare_"))
    pipeline = Pipeline(
        name="kyc_quality_compare",
        stages=[
            JsonlReader(file_paths=str(input_path)),
            ScoreFilter(filter_obj=filters, text_field="text"),
            JsonlWriter(path=str(out_dir)),
        ],
    )
    started = time.time()
    pipeline.run(XennaExecutor())
    kept = [row for f in out_dir.glob("*.jsonl") for row in read_jsonl(f)]
    return {row["chunk_id"] for row in kept}, round(time.time() - started, 1)


def main(chunks_path, curated_path, out_path):
    chunks = read_jsonl(chunks_path)
    all_ids = {c["chunk_id"] for c in chunks}
    ours_kept = {row["metadata"]["chunk_id"] for row in read_jsonl(curated_path)}
    doc_of = {c["chunk_id"]: c["doc_id"] for c in chunks}
    ours_removed = all_ids - ours_kept

    per_filter = []
    nemo_removed = set()
    for key, label, cls, params, ours in FILTERS:
        filt = cls(**params)
        removed = {c["chunk_id"] for c in chunks if not filt.keep_document(filt.score_document(c["text"]))}
        nemo_removed |= removed
        per_filter.append({
            "key": key, "label": label, "comparable_to": ours, "removed": len(removed),
            "also_removed_by_ours": len(removed & ours_removed),
        })

    pipeline_kept, seconds = run_nemo_pipeline(chunks_path, [cls(**params) for _, _, cls, params, _ in FILTERS])
    pipeline_removed = all_ids - pipeline_kept
    # Filters applied one at a time must agree with NeMo's own chained pipeline.
    assert pipeline_removed == nemo_removed, (len(pipeline_removed), len(nemo_removed))

    report = {
        "nemo_curator_version": nemo_curator.__version__,
        "executor": "XennaExecutor (CPU)",
        "pipeline_seconds": seconds,
        "input": "post-dedup chunks (same input as our quality filter)",
        "input_chunks": len(chunks),
        "nemo": {"kept": len(pipeline_kept), "removed": len(pipeline_removed)},
        "ours": {"kept": len(all_ids) - len(ours_removed), "removed": len(ours_removed)},
        "overlap": {
            "removed_by_both": len(nemo_removed & ours_removed),
            "only_nemo": len(nemo_removed - ours_removed),
            "only_ours": len(ours_removed - nemo_removed),
        },
        "filters": per_filter,
        "nemo_removed_by_doc": dict(Counter(doc_of[c] for c in nemo_removed).most_common()),
        "ours_removed_by_doc": dict(Counter(doc_of[c] for c in ours_removed).most_common()),
    }
    Path(out_path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("input_chunks", "nemo", "ours", "overlap")}, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
