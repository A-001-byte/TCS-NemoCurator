# BFSI/KYC Regulatory Data Curation Pipeline

Built for a TCS showcase (see `CONTEXT.md` / `LOOP.md` for the full brief). A curation
pipeline turns real Indian RBI/bank KYC-AML regulatory PDFs into a cleaned, deduplicated,
PII-redacted, fine-tuning-ready JSONL corpus, with a React dashboard visualizing every stage.

**No model was fine-tuned or trained.** That is the deliberate next stage (Megatron-Bridge)
in NVIDIA's own data-curation → training → deployment pipeline, and it is out of scope here.

## What is real

- All 19 input PDFs in `data/raw/` are real, publicly downloaded documents: the RBI Master
  Direction on KYC (2016, and updated variants), RBI Master Directions on fraud risk
  management, FIU-IND AML/CFT guidance and reporting formats, and published KYC/AML policy
  PDFs from Indian banks (Central Bank of India, Bank of Baroda, Canara Bank references,
  Nainital Bank, Equitas SFB docs, Bhiwani DCCB, Manappuram, etc.). No synthetic or
  fabricated input text was used.
- Text extraction, cleaning, language ID, exact + fuzzy deduplication, heuristic quality
  filtering, and PII redaction all genuinely run against that real extracted text — the
  counts on the dashboard (`docs_in`/`docs_out`/`removed` per stage, PII entities redacted,
  duplicates removed) are computed live by `pipeline/run.py`, not hardcoded.
- The PII before/after examples on the dashboard are real spans from real documents,
  redacted by the actual regex + spaCy NER pipeline at run time.

## What is not real / what is simulated

- **NeMo Curator itself is NOT integrated.** `pip install "nemo-curator[text_cpu]"` was
  attempted and failed on this machine: wheel builds for `fasttext` and `cosmos-xenna` fail
  without a C++ build toolchain on Windows. Per the build plan's fallback rule, every
  pipeline stage below is an **equivalent-logic reimplementation**, not a call into NeMo
  Curator's `ProcessingStage`/`Pipeline` API:
  - Quality filtering here is a heuristic (word count, alpha ratio, symbol ratio, lexical
    diversity) — NOT the shipped `nvidia/quality-classifier-deberta` classifier.
  - PII redaction here uses regex (PAN, Aadhaar-format, phone, email, DOB, PIN code,
    account numbers) plus spaCy's `en_core_web_sm` NER for person names — NOT NVIDIA's
    GLiNER-PII model.
  - Deduplication uses SHA-256 exact matching plus MinHash/LSH fuzzy matching via the
    `datasketch` library, following the same exact-then-fuzzy approach NeMo Curator uses,
    but reimplemented rather than invoked through the library.
  - These are clearly labeled "equivalent-logic stage, library integration pending" in the
    dashboard UI itself, not just in this file.
- No narrative-drafter / retrieval stage (Tier 2 in `LOOP.md`) is built in this pass unless
  a separate `dashboard` route says otherwise — check `STATUS.md` for current tier status.
- No fine-tuning, no model training, anywhere in this repository.

## Pipeline stage order (fixed, and matters)

```
extract → clean/normalize + language ID → dedup (exact, then fuzzy) → quality filter
→ PII redact → JSONL output
```

PII redaction runs **after** deduplication, never before. Deduplication depends on stable
content hashes; redacting PII first would replace matching strings inconsistently
(different placeholder text per occurrence) and silently break hash-based duplicate
detection. This ordering is itself a deliberate design decision, not an oversight.

## Running it

```bash
# 1. Python pipeline (from repo root)
python -m venv venv
source venv/Scripts/activate        # Windows Git Bash
pip install pdfplumber langdetect datasketch spacy
python -m spacy download en_core_web_sm
python -m pipeline.run

# 2. React dashboard (separate terminal)
cd dashboard
npm install
npm run dev
```

`pipeline/run.py` writes `data/output/pipeline_summary.json`. Everything the pipeline
writes under `data/` (except `data/raw/`) is untracked, so run it once after cloning.
The dashboard reads its own committed snapshot, `dashboard/public/pipeline_summary.json`,
which the pipeline no longer overwrites. To view your local numbers, copy
`data/output/pipeline_summary.json` over it, but do not commit that change: refreshing
the shared snapshot is a deliberate step owned by Stream D.

## Repository layout

```
data/raw/        real input PDFs
data/extracted/  per-PDF plain text
data/cleaned/    normalized text + language ID, one JSON record per doc
data/deduped/    surviving paragraph-level chunks after exact+fuzzy dedup
data/filtered/   surviving chunks after heuristic quality filtering
data/redacted/   PII-redacted chunks + pii_examples.json (before/after pairs)
data/output/     curated.jsonl (final fine-tuning-ready output) + pipeline_summary.json
pipeline/        each stage as an independent, restartable Python module
dashboard/       React (Vite) front end
```

## Where we deliberately stopped

```
Data Curation → Pre-training & SFT/LoRA → Post-training/RL → Inference
  [THIS REPO]     [Megatron-Bridge,          [RL]            [Export-Deploy,
                   AutoModel]                                  Eval, Guardrails]
```

We build only the leftmost box. Megatron-Bridge (training) is a separate, deliberately
out-of-scope stage.
