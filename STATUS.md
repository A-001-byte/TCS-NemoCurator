# Build Status
Last updated: 2026-09-17 00:52 IST

## Tier 0
- [x] T0.1 PDFs downloaded — 19 real RBI/bank KYC/AML PDFs downloaded, 19 valid (`data/raw/*.pdf`)
- [x] T0.2 Extraction — 18/19 extracted (1 image-only PDF failed cleanly, no crash: `bank_of_baroda_aml_questionnaire.pdf`)
- [x] T0.3 Pipeline end-to-end — `python -m pipeline.run` exits 0
- [x] T0.4 Deduplication — 148 chunks removed (1 exact, 147 fuzzy) out of 2395
- [x] T0.5 PII redaction — ~285 entities redacted (PINCODE, EMAIL, DATE, ACCOUNT_NUMBER, PHONE, PERSON_NAME); real before/after pairs in `data/redacted/pii_examples.json`. Person-name detection tuned for precision over recall (title-cue + shape filter) after an initial pass produced false positives on generic legal noun phrases — see `pipeline/pii.py` docstring.
- [x] T0.6 JSONL output — `data/output/curated.jsonl`, 2189 valid JSON lines, each with a `text` field
- [x] T0.7 React dashboard builds — `npm run build` exits 0; dev server verified serving with no console errors (checked via browser)
- [x] T0.8 Dashboard shows per-stage counts — funnel view matches pipeline_summary.json exactly
- [x] T0.9 Dashboard shows PII before/after — real redacted spans from real documents rendered in UI
- [x] T0.10 README honesty section — `README.md` "What is real / What is not" section written

**TIER 0 COMPLETE.**

## Tier 1
- [ ] T1.1 `pip show nemo-curator` — FAILED, not installed (see Fallbacks)
- [ ] T1.2 Real NeMo Curator `ProcessingStage`/`Pipeline` execution — not attempted, blocked by T1.1
- [x] T1.3 Dashboard/README label equivalent-logic stages clearly — done
- [ ] T1.4 Document-level drill-down in dashboard — not built (time permitting)

## Blockers
- None currently open.

## Fallbacks taken
- NeMo Curator install (`pip install "nemo-curator[text_cpu]"`) FAILED: wheel build errors for `fasttext` and `cosmos-xenna` (no C++ build toolchain on this Windows machine). Proceeded with equivalent-logic stages per LOOP.md rule 4, clearly labelled "NeMo-Curator-equivalent stage, library integration pending" in dashboard UI and README. T1.1/T1.2 marked failed, not faked.
- Initial paragraph-based chunking (split on blank lines) collapsed whole PDFs into single "paragraphs" because pdfplumber doesn't preserve blank-line paragraph breaks — switched to fixed 180-word chunking.
- Initial spaCy PERSON-name detection had a very high false-positive rate on dense legal/regulatory text (misclassifying phrases like "Gazette Notification" as names). Added a personal-title-cue requirement (Mr./Name:/Signatory/etc. nearby) — this trades recall for precision, so only 1 person name currently reported, but it is a real, verified name in the source document.
