# BFSI/KYC Regulatory Data Curation Pipeline

Banks and regulators publish long PDFs: RBI Master Directions, FIU-IND guidelines, bank and NBFC KYC policies. Before a language model can be fine-tuned on them, the text has to be cleaned: page furniture removed, copies removed, personal data hidden, useful passages labelled. This repository does that automatically. You give it a folder of PDFs and it returns a fine-tuning-ready JSONL file, plus a dashboard that shows what every stage removed or changed and why.

Built for the TCS showcase on the ideas of NVIDIA NeMo Curator. **No model is trained here.** Fine-tuning (NVIDIA's Megatron-Bridge stage) is the next step in NVIDIA's data-curation → training → deployment chain and is out of scope.

## Numbers (full run on 35 PDFs, 20 Oct 2026)

| Step | Result |
|---|---|
| PDFs in / readable | 35 / 34 (one scanned PDF has no text layer and is reported, not crashed on) |
| Page-furniture lines removed (heal) | 3,176 in 28 repeating patterns |
| Chunks entering dedup | 3,726 |
| Removed by dedup | 330: 3 exact, 290 boilerplate repeated across documents, 37 near-copies inside one document |
| Removed by quality filter | 71: 62 mostly numeric, 8 symbol-heavy, 1 repetitive |
| **Final chunks** | **3,325** (about 596,000 words) |
| Tagged as regulatory | 1,913 (57.5%), 821 of them with high regulatory density |
| Personal-data items hidden | 68: 47 email, 13 PIN code, 3 phone, 2 company ID (CIN), 2 person name, 1 SWIFT code |

The PII figure is mostly official contact details printed in public documents (government emails, office PIN codes), which the pipeline hides anyway. It does not claim to have found private data.

## What is real, and what is not

**Real**
- All 35 input PDFs in `data/raw/` are public documents from the original sources (RBI, FIU-IND, SEBI/AMFI, bank and NBFC websites, law-firm summaries). Nothing is synthetic.
- Every count on the dashboard is computed by the pipeline, not typed in.
- **Real NVIDIA NeMo Curator 1.3.0** was installed on a Linux VM and run on the same chunks as our quality stage (`pipeline/nemo_compare.py`, `XennaExecutor` on CPU). Its default filters remove **716 of 3,396** chunks (21.1%); our quality stage removes **71** (2.1%); 67 are removed by both. 550 of NeMo's removals come from its duplicated-5-gram filter and 434 from two FIU report-format guides, which are tables of repeated field descriptions. NeMo's defaults are tuned for web text, so this shows a difference in design, not that either side is wrong; we have not hand-checked the 649 chunks only NeMo removes.
- The 16 newest documents were never used when the rules were tuned. Running them found 7 false PII alarms (digits inside statistics tables and placeholders such as `0000000000`), which are now rejected (PII 75 → 68). Details in `docs/IMPROVEMENT_LOG.md`.

**Our own implementations ("equivalent-logic" stages), not calls into NeMo**
- **Dedup:** SHA-256 exact matching plus MinHash/LSH fuzzy matching (`datasketch`), run on the CPU. NeMo's own dedup needs a GPU (`docs/A1_3_dedup_gpu_finding.md`). When several versions of one policy exist, the newest is kept.
- **Quality filter:** heuristics (alpha ratio, symbol ratio, lexical diversity, minimum words) plus regulatory-keyword tagging. NVIDIA's DeBERTa quality classifier was tested and **rejected as a filter** because it is about 17x stricter and judges layout, not quality (`docs/A1_4_quality_classifier_comparison.md`). It remains as an optional, off-by-default label (`QUALITY_SIGNAL_MODE`, `pipeline/quality.py`) that never removes a chunk.
- **PII:** regex plus spaCy, with context checks: dates only after a birth cue, PIN codes only with an address context, Aadhaar by Verhoeff checksum, SWIFT only with a label, and account numbers only with a bank cue and not inside numeric tables. GLiNER is available behind `USE_GLINER_PII` (off by default).

**Document-type classifier (small, honestly scored).** A nearest-centroid classifier over 6 document types, built on the clause-search TF-IDF (`dashboard/src/doctype.js`). With each document's whole near-copy family held out it scores **55.9%** against **29.4%** for always guessing the biggest type. Four combinations were scored on the same 34 documents and two types were merged after seeing the confusion table, so treat this as the optimistic end; `fiu_reporting_spec` is still 0%. It is not a trained fraud or anomaly model. Results: `dashboard/public/doctype_eval.json`.

**Not built:** OCR for scanned PDFs, any model training, a hosted/cloud API. All stages currently run on the CPU; automatic GPU/CPU selection is being added (see `STATUS.md`).

## How it works: 7 stages (the order matters)

```
extract → clean + language ID → heal → dedup → quality filter → PII redact → JSONL output
```

| # | Stage | What it does |
|---|---|---|
| 1 | extract | Reads text from each PDF (`pdfplumber`). Image-only PDFs fail cleanly and are counted. |
| 2 | clean + language ID | Normalises text; drops anything too short or not English. |
| 3 | heal | Removes page furniture (repeated letterheads, footers) and repairs words split by the PDF layout, so furniture cannot hide duplicates or pose as PII. |
| 4 | dedup | Exact then fuzzy; keeps the newest policy version; separates boilerplate shared across documents from copies inside one document. |
| 5 | quality filter | Drops numeric, symbol-heavy and repetitive chunks; tags regulatory vocabulary and density. |
| 6 | PII redact | Replaces personal data with `[REDACTED_TYPE]` placeholders. |
| 7 | output | One JSON line per chunk: `{"text": ..., "metadata": {...}}`. |

PII redaction runs **after** dedup on purpose: dedup relies on stable content hashes, and redacting first would write different placeholder text per occurrence and silently break duplicate detection. Heal runs **before** dedup for the reason in the table.

Each stage writes a record `{stage, docs_in, docs_out, removed, reason_counts}`; output lines carry `{text, metadata}`. These two shapes are frozen: fields may be added, never renamed or removed.

## Quick start

```bash
# 1. Python environment (repo root). On Linux/macOS use venv/bin/activate
python -m venv venv
source venv/Scripts/activate            # Windows Git Bash
pip install pdfplumber langdetect datasketch spacy
python -m spacy download en_core_web_sm
```
A pinned `requirements.txt` is being added; until then the line above is the CPU install. `gliner`, `torch` and `transformers` are only needed for the optional components.

**Use it as a library**
```python
from pipeline.api import curate
result = curate("pdfs/", "out/")                 # runs all 7 stages on every *.pdf in pdfs/
print(result.summary["final_output_chunks"])     # out/curated.jsonl and out/pipeline_summary.json are written
```

**Use it from the terminal**
```bash
pip install -e .                                 # installs the `bfsi-curate` command
bfsi-curate run pdfs/ -o out/ --device auto
python -m pipeline.cli run pdfs/ -o out/         # same thing without installing
```

**Run the whole corpus and the dashboard**
```bash
python -m pipeline.run                           # data/raw -> data/output/curated.jsonl + pipeline_summary.json
python -m pipeline.server                        # API on 127.0.0.1:8000 (POST /api/run uploads PDFs)
cd dashboard && npm install && npm run dev       # dashboard; /api is proxied to the server above
```
The library, the CLI and `POST /api/run` all call the same code (`pipeline/api.py`), and a test checks that they return identical output. Every library or API run happens in a temporary folder, so `data/` is not touched. Everything under `data/` except `data/raw/` is untracked and regenerated by the pipeline. The dashboard reads committed snapshots in `dashboard/public/` (`pipeline_summary.json`, `curated.jsonl`, `nemo_comparison.json`, `doctype_eval.json`); a refresh script for them is in progress (see `STATUS.md`).

## Tests

```bash
python -m pipeline.test_server        # upload path
python -m pipeline.test_api_parity    # library == CLI == HTTP API
python -m pipeline.test_pii_rules     # also: test_pii_validation, test_pii_names, test_pii_gliner
python -m pipeline.test_dedup_versions
python -m pipeline.test_heal_changelog
python -m pipeline.test_quality_tags  # also: test_quality_signal
cd dashboard && npm test              # document-type classifier (7 tests)
```
Rules that changed behaviour have a test that fails when the rule is broken.

## Repository layout

```
data/raw/        the 35 source PDFs (the only tracked folder under data/)
data/extracted/ cleaned/ healed/ deduped/ filtered/ redacted/ output/   per-stage results (untracked)
pipeline/        one module per stage, plus api.py (library), cli.py, server.py, nemo_compare.py,
                 doc_type_labels.json, doc_type_families.json, test_*.py
dashboard/       React (Vite) front end; src/doctype.js is the document-type classifier
docs/            IMPROVEMENT_LOG.md (every change with before/after numbers), A1_* findings,
                 evidence/stream-c/ (PII evidence), team/ (the team's evidence), demo/, archive/;
                 see docs/README.md for the index
SETUP.md         Linux / WSL2 setup used for real NeMo Curator
```

## Where we deliberately stopped

```
Data Curation → Pre-training & SFT/LoRA → Post-training/RL → Inference
  [THIS REPO]     [Megatron-Bridge,          [RL]            [Export-Deploy,
                   AutoModel]                                  Eval, Guardrails]
```
