# Improvement log

Numbers in this file come from real runs on the date shown. Nothing here is estimated.

## Phase 0: Baseline (2026-10-04)

Commit: `2c4d71b` (main, includes PR #6 `e3f6fb0` and PR #7). Python 3.11 (repo `venv`), Windows.
Command: `python -m pipeline.run` (exit 0).

### BASELINE TABLE

| Stage | in | out | removed / reasons |
|---|---|---|---|
| extract | 19 PDFs | 18 | 1: `extraction_failed` (`bank_of_baroda_aml_questionnaire.pdf`, empty extraction) |
| clean_langid | 18 | 18 | 0 (too_short 0, non_english 0) |
| dedup | 2395 chunks | 2247 | 148: exact 1, cross_doc_boilerplate 122, intra_doc_near_duplicate 25 |
| quality_filter | 2247 | 2189 | 58: low_alpha_ratio 34, low_lexical_diversity 24 |
| pii_redact | 2189 | 2189 | 0 removed; 284 entities redacted |
| output | 2189 | 2189 | 2,533,754 characters |

PII (284 entities): PINCODE 241, EMAIL 32, DATE 4, PHONE 3, CIN 2, SWIFT_BIC 1, PERSON_NAME 1.
`chunks_with_pii` 248, `documents_with_pii` 11, `account_numbers_suppressed` 4,
`account_numbers_needs_review` 0, `swift_candidates_rejected_no_cue` 153, `chunks_needing_review` 0,
`name_detection_available` true.

Regulatory tags: 2019 tagged / 170 untagged of 2189 (92.2% tagged), 631 high-density.

**Difference from the expected table in the prompt: none.** Every number matched.
**Difference from the committed `dashboard/public/pipeline_summary.json`:** only
`stages[output].output_path` (this run: absolute Windows path; committed file:
`/home/kali/TCS-NemoCurator/...`). `pii_examples` and `documents` are identical.
Both absolute paths are a Phase 8 fix (repo-relative path).

### Tests

| Command | Result |
|---|---|
| `python -m pipeline.test_pii_validation` | pass |
| `python -m pipeline.test_heal_changelog` | pass |
| `python -m pipeline.test_server` | pass (8 chunks, 7 PII entities for `bank_of_baroda_kyc.pdf`) |

All three are assert-scripts with `main()`, so `pytest` would collect nothing (Phase 9).

### How the dashboard snapshots are refreshed today

**They are not refreshed by any script.** `pipeline/run.py` writes only `data/output/`; its
header comment says the dashboard snapshot "Stream D refreshes on purpose". The three files in
`dashboard/public/` were each copied by hand, by different people, at different times:

| File | Source | History |
|---|---|---|
| `pipeline_summary.json` | copy of `data/output/pipeline_summary.json` | hand-copied in several commits (Ankit, Kunal, Aditi, Saachi; last 2026-09-23) |
| `curated.jsonl` | copy of `data/output/curated.jsonl` | added by Saachi (`b2deffd`), refreshed by hand |
| `nemo_comparison.json` | `python -m pipeline.nemo_compare` run on the Ubuntu VM, then `scp` | created in PR #6 |

Consequence: the dashboard can silently drift from the code. Plan: Phase 8 adds
`scripts/refresh_dashboard_snapshot.py` (applies PII masking) and a "Re-run pipeline" button
on the dashboard backed by `pipeline/server.py`, with a test. It is deferred to Phase 8 on
purpose: the refresh has to apply the Phase 8 masking and see the Phase 1 heal stage.

### Other observations (no action taken in Phase 0)

- `pattern/` (`matcher.js`, `test.js`) still exists (Phase 5 deletes it).
- No `scripts/` folder and no `requirements*.txt` yet (Phase 8).
- `data/healed/` exists locally from an earlier standalone `heal` run and is git-ignored.

## Phase 1: Page-Splice Healing wired into the pipeline (2026-10-04)

Branch `fix/p1-heal-wiring`. Stage order is now `extract -> clean_langid -> heal -> dedup -> quality_filter -> pii_redact -> output`.
`HEAL_ENABLED = True` in `pipeline/heal.py`; with it `False`, run.py skips heal and dedup reads `data/cleaned`
(verified: reproduces the Phase 0 table exactly, 2395 -> 2247 -> 2189, 284 entities, same per-type counts).

### Before -> After (full corpus, real runs)

| Metric | Phase 0 (no heal) | Phase 1 (heal on) |
|---|---|---|
| Chunks entering dedup | 2395 | 2284 |
| Dedup removed | 148 (exact 1, cross-doc 122, intra-doc 25) | 200 (exact 1, cross-doc 162, intra-doc 37) |
| Quality filter removed | 58 (alpha 34, diversity 24) | 200 (alpha 33, symbol 1, **diversity 166**) |
| Final chunks | 2189 | 1884 |
| Final characters | 2,533,754 | 2,162,849 |
| PII entities | 284 | 65 |
| PINCODE | 241 | 24 |
| EMAIL | 32 | 30 |
| DATE / PHONE / CIN / SWIFT_BIC / PERSON_NAME | 4 / 3 / 2 / 1 / 1 | 4 / 3 / 2 / 1 / 1 |
| Chunks with PII | 248 | 34 |
| SWIFT candidates rejected (no cue) | 153 | 143 |
| Regulatory tagged / untagged / high-density | 2019 / 170 / 631 | 1648 / 236 / 586 |
| Output chunks containing Devanagari | not measured | 0 |
| Output chunks containing a page marker | not measured | 7 |

Heal stage record: 18 docs in, 18 out, 0 removed; 2,536 furniture lines deleted (19 signatures), 20 kerning splits repaired.
Purity (pre-quality-filter chunks), before -> after: Devanagari 242 -> 0, page markers 637 -> 7, PIN-code-shaped numbers 252 -> 24, duplicate chunks 148 -> 200.
These match `docs/evidence/stream-c/heal_stage_record.json`.

### Expected, not bugs
- **Duplicates go UP (148 -> 200).** Letterheads made otherwise-identical chunks look different; after healing they match.
- **PINCODE 241 -> 24.** About 90% of the old "PII" was one bank's letterhead address repeated on every page.

### Surprising: the quality filter now removes 200 chunks, not 58 (NOT changed, needs a decision)
`low_lexical_diversity` jumped 24 -> 166. 176 of the 200 removed chunks are from `fiu_india_reporting_format`
(34 removed before). That document is a form schema made of repeated field names. Before healing, every chunk also
carried the footer "Financial Intelligence Unit - India (FIU-IND) Page | n", whose extra unique words kept the chunk above
`MIN_LEXICAL_DIVERSITY = 0.30`. With the footer gone, the real content falls below the threshold.
`docs/A1_4_quality_classifier_comparison.md` already argued that this kind of structured form content is valuable to keep.
`quality.py` is Stream B's file and the threshold is theirs, so this phase leaves it alone.
Options: lower the threshold for form-structured documents, exempt them, or accept the loss. Needs a user decision.

### Checks
- Stage-record contract asserted on all 7 stages (keys `stage, docs_in, docs_out, removed, reason_counts`; `removed == docs_in - docs_out`): OK.
- Output records are `{text, metadata}` with all existing metadata keys: OK (1884 lines).
- Tests: `test_pii_validation`, `test_heal_changelog` (now incl. `heal_documents` on 2 synthetic docs and the dedup loader), `test_server` (uploaded PDF run includes the heal stage): all pass.
- `python -m pipeline.heal` and `python -m pipeline.changelog` standalone: exit 0.

### Not done / caveats
- `dashboard/public/pipeline_summary.json`, `curated.jsonl`, `nemo_comparison.json` are NOT refreshed in this phase, so the
  live dashboard still shows the Phase 0 numbers until Phase 8's refresh script. `nemo_comparison.json` also needs a re-run on
  the Curator VM because its input chunks changed. The new heal panel was checked by temporarily serving the new summary
  (restored afterwards; nothing committed).
- Correct changelog baseline: `changelog.py` is unchanged and still works (heal writes `data/healed`, raw text from `data/cleaned`).
