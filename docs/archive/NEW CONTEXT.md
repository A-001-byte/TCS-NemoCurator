# PROJECT CONTEXT v2 — Read This First

Shared by all four teammates. Every loop file (`LOOP-A.md` through `LOOP-D.md`) assumes
you've read this. If your loop file conflicts with this file on a fact, this file wins —
flag the conflict to the team rather than picking one silently.

---

## 1. WHERE WE ARE NOW

The overnight build (v1) succeeded. Presentation went well. **TCS has committed: build
the full project over 2-3 weeks.** This is no longer a one-evening survival build — treat
it as a real project with real runway, but don't let that turn into scope creep either.

Repo: `github.com/A-001-byte/TCS-NemoCurator`

### What already exists and works (verified against real repo data, not assumed)

- 19 real RBI/bank KYC-AML PDFs in `data/raw/`
- Full pipeline runs end to end: extract → clean/langid → dedup → quality filter →
  PII redact → output
- Real results: 148 chunks deduplicated (1 exact, 147 fuzzy) out of 2,395; ~285 PII
  entities redacted across PINCODE/EMAIL/DATE/ACCOUNT_NUMBER/PHONE/PERSON_NAME
- React (Vite) dashboard showing per-stage funnel counts, PII before/after, per-document
  drill-down
- **NeMo Curator itself is NOT installed.** Every stage is an "equivalent-logic"
  reimplementation, clearly labelled as such in README and the dashboard UI. Install
  failed on Windows: `fasttext`/`cosmos-xenna` wheel builds need a C++ toolchain not
  present on the dev machine.

### What TCS actually asked for, in the follow-up meeting

Direct asks from the TCS contact, most recent meeting:

1. **"Add custom filtration — validation, deduplication, anything — alongside Curator."**
   He said this to multiple groups; he wants to see custom rules layered on top of
   curation, not just default library calls.
2. **The real end goal:** a model that, given new incoming KYC data, recognizes it
   against **learned patterns** — closer to anomaly/classification than plain cleanup.
   Today's pipeline is the data-prep stage that feeds that; it is not that model itself.
3. Full working project in 2-3 weeks.

### Known team facts

- 4 teammates now, working in parallel via separate Claude Code loops.
- Team has previously been "unreliable" per earlier notes — mitigate by making each
  stream's scope small enough that one person's slip doesn't block the other three.

---

## 2. THE FROZEN INTERFACE CONTRACTS — DO NOT CHANGE WITHOUT TEAM AGREEMENT

This section is why four parallel loops don't turn into integration hell. Every stream
builds against these exact shapes. If a shape needs to change, that's a team conversation,
not a unilateral edit — a schema change breaks every other stream silently.

### Contract 1 — the chunk record (used dedup → quality → pii → output)

```json
{
  "chunk_id": "bank_of_baroda_kyc__3",
  "doc_id": "bank_of_baroda_kyc",
  "source_file": "bank_of_baroda_kyc.pdf",
  "text": "...chunk text...",
  "pii_redacted": true
}
```

`chunk_id` = `{doc_id}__{index}`. `pii_redacted` only appears after the PII stage runs;
earlier stages don't include it.

### Contract 2 — the cleaned document record (extract → clean output)

```json
{
  "doc_id": "bank_of_baroda_kyc",
  "source_file": "bank_of_baroda_kyc.pdf",
  "text": "...full cleaned document text...",
  "lang": "en",
  "char_count": 48213
}
```

### Contract 3 — stage record (every stage writes one, orchestrator reads it)

```json
{
  "stage": "quality_filter",
  "docs_in": 2247,
  "docs_out": 2189,
  "removed": 58,
  "reason_counts": {"too_few_words": 12, "low_alpha_ratio": 9, "...": "..."}
}
```

Any new stage or sub-stage MUST emit this shape so the dashboard and orchestrator keep
working without changes.

### Contract 4 — final output record (`data/output/curated.jsonl`)

```json
{
  "text": "...redacted chunk text...",
  "metadata": {
    "chunk_id": "bank_of_baroda_kyc__3",
    "doc_id": "bank_of_baroda_kyc",
    "source_file": "bank_of_baroda_kyc.pdf",
    "pii_redacted": true
  }
}
```

**Stream D builds against a frozen copy of the CURRENT `curated.jsonl` and
`pipeline_summary.json`** (copy them out today, before A/B/C start changing the
pipeline) so the dashboard/pattern work never blocks on pipeline changes landing first.

### Adding a field is fine. Removing or renaming one is not, without a team sync.

---

## 3. GIT WORKFLOW FOR FOUR PARALLEL STREAMS

- One branch per stream: `stream-a-curator`, `stream-b-filters`, `stream-c-pii`,
  `stream-d-dashboard`.
- Each stream owns specific files (see each LOOP file's "Files you own" section).
  **Never edit a file another stream owns**, even a small fix — flag it to them instead.
- Merge order matters least for A (mostly swaps internals behind the same contracts).
  B and C touch adjacent pipeline files but different functions — low conflict risk if
  contracts hold. D never touches pipeline code, only reads frozen JSON — zero conflict
  risk by construction.
- Merge to `main` when a stream's Tier 0 is green, not before. Don't merge half-finished
  work that breaks `python -m pipeline.run` for everyone else.

---

## 4. TECHNICAL FACTS CARRIED OVER FROM v1 (still true, still matters)

- **NeMo Curator 1.x is a rewrite.** `ProcessingStage` objects composed into a
  `Pipeline`, run via an executor. Old `DocumentDataset`/`nemo_curator.modules.*` from
  0.x is gone. Most tutorials online are 0.x — don't copy their imports.
- **PII redaction runs AFTER deduplication, never before.** Dedup depends on stable
  content hashes; redacting first corrupts them inconsistently. This is a permanent rule
  for any new PII logic (Stream C), not just the current implementation.
- Quality classifier NeMo Curator ships: `nvidia/quality-classifier-deberta`.
- PII model NeMo Curator ships: GLiNER-PII (`gliner_pii_redaction.ipynb` in their repo).
- Megatron-Bridge is the next stage after curation (pretraining/SFT/LoRA) — still
  explicitly out of scope for this project. We stop at producing curated, fine-tuning-
  ready data.
- Indian-specific PII formats already handled: PAN (`AAAAA9999A`), Aadhaar-shape
  (12-digit), Indian phone/mobile, 6-digit pincode, generic account-number-length runs.
- The name-detection precision fix (title-cue requirement to avoid false positives like
  "Gazette Notification") is a real, hard-won result — don't regress it while extending
  Stream C.

---

## 5. THE FOUR STREAMS AT A GLANCE

| Stream | Scope | Files owned | Loop file |
|---|---|---|---|
| A | Get real NeMo Curator installed and swap equivalent-logic stages for real API calls | New: environment/install scripts. Modifies: internals of `extract.py`/`quality.py`/`pii.py`/`dedup.py` behind existing contracts | `LOOP-A.md` |
| B | Custom filtration: domain-keyword routing, regulatory-boilerplate-aware dedup | `pipeline/quality.py`, `pipeline/dedup.py` | `LOOP-B.md` |
| C | Custom validation: more entity types, cross-field coherence checks | `pipeline/pii.py` | `LOOP-C.md` |
| D | Dashboard extension + first pass at the pattern/classification scenario | `dashboard/`, new `pattern/` module | `LOOP-D.md` |

Read your own loop file for full detail. This file is background all four share.

---

## 6. STYLE / COMMUNICATION

Buster prefers direct, casual, blunt communication. Honest assessments over encouragement.
No padding. Flag uncertainty explicitly. If something can't be done in the time available,
say so immediately rather than half-building it. This applies to what every loop reports
back, not just chat replies.
