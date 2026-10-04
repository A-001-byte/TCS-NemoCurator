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
(34 removed before). That document is a form schema made of repeated field names. Before healing, every page also carried
two header/footer lines ("Reporting Format - Introduction Version 1.0" and "Financial Intelligence Unit - India (FIU-IND)
Page | n"; 538 pages each, 1,076 lines removed by healing). Their ~dozen extra unique words kept each chunk above
`MIN_LEXICAL_DIVERSITY = 0.30`. With the lines gone, the real content falls below the threshold.
`docs/A1_4_quality_classifier_comparison.md` already argued that this kind of structured form content is valuable to keep.
`quality.py` is Stream B's file and the threshold is theirs, so this phase leaves it alone.
Options were: lower the threshold, exempt form documents, or accept the loss. **Resolved in Phase 1b below (cutoff 0.20).**

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

## Phase 1b: lexical-diversity cutoff 0.30 -> 0.20 (2026-10-04)

Branch `fix/p1b-diversity-threshold` (stacked on Phase 1). One constant in `pipeline/quality.py` (Stream B's file).

### Why 0.20
Measured on the 2084 post-dedup healed chunks (and 2247 unhealed), quality filter removals by cutoff:

| Cutoff | Removed, unhealed | Removed, healed | FIU form chunks kept (healed) |
|---|---|---|---|
| 0.30 | 58 | 200 | 400 / 576 |
| 0.25 | 38 | 51 | 549 / 576 |
| **0.20** | **34** | **35** | **561 / 576** |
| 0.15 | 34 | 34 | 562 / 576 |
| 0.10 | 34 | 34 | 562 / 576 |

Chunks between 0.20 and 0.30 (177 healed: FIU form 161, ebixcash 11, slbc 5) were read by hand: field definitions,
address-validation rules, lists of circular numbers. All valid content.

Synthetic junk test (180-word chunks, real `quality_reason`): stutter, repeated line, OCR loop, header spam and menu spam
(scores 0.01-0.06) are removed at every cutoff down to 0.10. Random text from a small vocabulary is caught only above its
own score: 20-word vocabulary (0.11) down to 0.15, 30-word (0.17) down to 0.20, 40-word (0.23) down to 0.25. No cutoff
separates the middle zone perfectly (a real FIU table chunk scores 0.19, below the 0.23 junk). 0.20 was chosen over 0.15
because 0.15 misses the 30-word-vocabulary junk, at the cost of one valid chunk (`fiu_india_reporting_format__540`, 0.19).
The small-vocabulary junk is synthetic and probably rare; this is a judgment call, not a proof.

### The 33 alpha-ratio removals (read in full, NOT changed)
17 tables of contents / cover pages (dot leaders count as non-letters; includes one revision-history chunk,
`reporting_format__2`, and `ebixcash__0`, which mixes a title block with a TOC), 15 lists of superseded circular numbers
and dates (`ebixcash` 8, `slbc_mp` 7), and 1 real prose chunk (`slbc_mp__77`, alpha 0.46 vs cutoff 0.50). Same content types
with or without healing. Judged mostly correct removals (navigation / bibliography). Lowering the alpha cutoff to 0.45
would rescue `slbc_mp__77` but also admit a TOC (`fiu_india_aml_cft_guidelines_2023__1`, 0.45), so it was left alone.
Correction to an earlier statement: the FIU chunks removed by alpha ratio are tables of contents, not form tables.

### Result (full corpus, real run, exit 0)

| | Phase 0 (no heal) | Phase 1, cutoff 0.30 | Phase 1b, cutoff 0.20 |
|---|---|---|---|
| Quality filter removed | 58 (diversity 24) | 200 (diversity 166) | **35 (diversity 1)** |
| Final chunks | 2189 | 1884 | **2049** |
| Final characters | 2,533,754 | 2,162,849 | 2,350,012 |
| FIU reporting-format chunks kept | 601 | 400 | 561 |
| PII entities | 284 | 65 | 65 |
| Regulatory tagged / untagged / high-density | 2019 / 170 / 631 | 1648 / 236 / 586 | 1781 / 268 / 596 |

Stage-record contract OK on all 7 stages; output chunks with Devanagari 0, with a page marker 7; the three tests pass.

## Phase 2: dedup keeps the NEWEST policy version (2026-10-04)

Branch `fix/p2-dedup-newest` (stacked on Phase 1b). New `pipeline/versioning.py` (shared by `dedup.py` and `changelog.py`, no import cycle);
`dedup.build_chunks()` now visits documents newest first, so the first (surviving) copy of a shared chunk belongs to the latest version.

Year source: (1) filename/doc_id (`2024_25` -> 2025, `2021`, `aug2025`), (2) `version_year(text)` = latest year mentioned in the text, (3) 0.
Ties broken by doc_id. Caveat (also in the helper's docstring): the text fallback takes the MAX year, so a document citing a future
deadline is mis-ordered, which is why the filename wins. Visible here: `nainital_bank_kyc_aml_policy` gets 2026 from its text.
That only reorders ties between different banks' documents, not versions of one policy.
`changelog.py` imports `version_year` from the new module; its behaviour and ordering are unchanged.

### Per-document chunks surviving dedup (before -> after)

| Document | Before | After |
|---|---|---|
| central_bank_india_kyc_aml_2021 (oldest) | 211 | 187 |
| central_bank_india_kyc_aml_2024_25 | 266 | 191 |
| central_bank_india_kyc_aml_2025_26 (newest) | 188 | **283** (of 283) |
| rbi_kyc_updated_aug2025_allinonebanking | 22 | 40 |
| rbi_kyc_ebixcash | 156 | 138 |
| bhiwani / manappuram / nainital | 201 / 90 / 202 | 198 / 91 / 206 |
| all other documents | unchanged | unchanged |

Before this fix the OLDEST Central Bank policy kept every chunk (211 of 211) while the NEWEST lost 95 of 283.

### Totals

| | Phase 1b | Phase 2 |
|---|---|---|
| Dedup removed | 200 (exact 1, cross-doc 162, intra-doc 37) | 202 (exact 1, cross-doc 164, intra-doc 37) |
| Chunks after dedup | 2084 | 2082 |
| Quality removed | 35 | 35 |
| Final chunks | 2049 | 2047 |
| Final characters | 2,350,012 | 2,347,736 |
| PII entities / PINCODE | 65 / 24 | 65 / 24 |
| Regulatory tagged / untagged / high-density | 1781 / 268 / 596 | 1780 / 267 / 593 |

Total duplicates barely move (as expected: ordering changes WHICH copy survives, not how many are copies). 123 chunk ids dropped out and
121 new ones came in. Contract OK on all 7 stage records.

### Tests
New `pipeline/test_dedup_versions.py`: filename/FY-pair parsing, text fallback and its caveat, newest-first ordering and tie-break,
and two synthetic versions `policy_2021` / `policy_2025` sharing a chunk: the surviving copy is `policy_2025__0`, whichever order the input
arrives in, and results are deterministic. Mutation-checked: it fails when dedup is switched back to filename order.
All four tests pass; `pipeline.changelog` still exits 0.

## Phase 3: PII precision rules (2026-10-04)

Branch `fix/p3-pii-rules` (stacked on Phase 2). All in `pipeline/pii.py` (Stream C). New tests: `test_pii_rules.py`,
`test_pii_gliner.py`, `test_pii_names.py`.

### What the real data showed before any rule changed
The 24 PIN codes still redacted after healing were: **6 genuine address PINs** (Nainital 263001, New Delhi 110001 x3,
Baroda 390006/390007), **17 money amounts** from a Central Bank threshold table ("Urban 150000 ..."), and **1 phone-number tail**
(`Phone: 05942-233739`). All 4 DATE hits were public regulatory/form-signature dates, none a date of birth. The corpus contains
no Aadhaar numbers, so that rule is only exercised by synthetic tests.

### Rules
| Rule | Change |
|---|---|
| 3a DATE | Redact only after a DOB cue (`DOB`, `D.O.B`, `date of birth`, `born`) within 30 chars on the same line. Matcher accepts `/ - .` separators and 1-2 digit day/month. |
| 3b PINCODE | Accept only with a PIN label right before it, or directly after a place name + hyphen/comma/dash (`Mumbai-400001`, `New Delhi - 110001`). Reject right after a money word (`Rs`, `INR`, `amount`, `above`, `exceeding`, `threshold`, `of`) and prefixes below 11. The PINCODE *shape* regex is unchanged, because `heal.py` counts PIN-shaped spans with it. |
| 3c AADHAAR | First digit 2-9; separators space/hyphen only (no newline); Verhoeff checksum (own implementation, checked against the standard vector 2363). Valid: redact. Invalid + Aadhaar/UID label within 60 chars: redact and count `aadhaar_needs_review`. Otherwise: left alone, counted in `aadhaar_candidates_rejected`. |
| 3d GLiNER | Block moved above `main()`; `main()` now calls it when `USE_GLINER_PII` is True (default False). Overlaps resolved by score, then length, then position, then applied from the end (the old code could corrupt text when different labels overlapped). Lazy import with a clear `RuntimeError` if `gliner` is missing, no silent fallback. `GLINER_PERSON_GUARD = True` keeps the title-cue + name-shape test on GLiNER PERSON spans; `GLINER_ENABLED_TYPES` can restrict GLiNER to e.g. PHONE/EMAIL. |
| 3e PERSON_NAME | New narrow rule: initials+surname or 2+ ALL-CAPS words, only directly after Shri/Smt/Mr/Mrs/Ms/Dr; job titles and common words blocked. Labelled set: 8 positives found, 17 negatives untouched. |

### Deviations from the brief (code wins, per rule 10)
- PIN money cue is anchored to the number (`... of 100000`, `Rs. 500000`) instead of "anywhere within ~15 chars", because "of" in
  `Bank of Baroda-390006` would have rejected a real address.
- Prefix rule rejects `10xxxx` (no such PIN range); `00xxxx` cannot match the shape in the first place.
- With the spaCy model unavailable, the title-gated name rule still runs (it needs no model); `name_detection_available` still reports spaCy only.
- A checksum-failing Aadhaar-shaped number written with NO separators and no label is still caught by the later 9-18 digit
  ACCOUNT_NUMBER rule (as `needs_review`); spaced forms are not.

### Before -> After (full corpus, real run)
| | Phase 2 | Phase 3 |
|---|---|---|
| PII entities | 65 | **43** |
| PINCODE | 24 | **6** (the six real address PINs) |
| DATE | 4 | **0** (48 date-shaped candidates rejected, incl. dd.mm.yyyy) |
| EMAIL / PHONE / CIN / SWIFT_BIC / PERSON_NAME | 30 / 3 / 2 / 1 / 1 | 30 / 3 / 2 / 1 / 1 |
| Chunks with PII | 34 | 30 |
| PIN candidates rejected (no cue / money or prefix) | n/a | 13 / 5 |
| Aadhaar candidates / needs_review | n/a | 0 / 0 |
| Title-gated name matches in the real corpus | n/a | 0 |
| Final chunks | 2047 | 2047 |

Versus the Phase 0 baseline: PII entities 284 -> 43; PINCODE 241 -> 6.
The 30 remaining emails are public contact addresses (nodal officers, bank offices); not changed.

### Honest limits
- The Aadhaar rule and the new name rule found nothing in the real corpus; they are validated on synthetic and labelled strings only.
- The new PIN rule keeps only what it can tie to a place name or label. A real PIN written as bare "Mumbai 400001" (no hyphen/comma, no label) would now be missed; none exist in this corpus.
- Remaining PIN codes are institutional office addresses in public regulatory documents, not personal data. They are still redacted
  (cheap and safe) but the dashboard now calls them "Address PIN code".

### Evidence
`docs/evidence/stream-c/` regenerated (`pii_stage_record.json`, `validation_report.json` changed; heal and changelog files came out identical).
`pii_examples.json` is deliberately not copied (raw values).

### Not done / still pending
- `dashboard/public/*` snapshots not refreshed (Phase 8); `App.jsx` does not yet show the new rejection counters (Phase 8, with the refresh).
- Tests: all seven scripts pass; `pytest` conversion is Phase 9.
