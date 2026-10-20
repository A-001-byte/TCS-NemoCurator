# Project Status

Last updated: Wednesday 21 Oct 2026. Final review: Thursday 22 Oct 2026, morning, in person.
Owners and gates are in `docs/team/01_WORK_PLAN.md`; every change with before/after numbers is in `docs/IMPROVEMENT_LOG.md`.

## Done (with the evidence)

| Area | Evidence |
|---|---|
| 7-stage pipeline on 35 PDFs (34 readable): 3,325 final chunks, 68 PII items hidden | `python -m pipeline.run`; numbers table in `README.md` |
| 16 new source documents added; used as an untouched test of the earlier rules | PR #14. Found 7 false PII alarms (tables, placeholders), fixed: PII 75 → 68 |
| One code path for library, terminal command and HTTP API | PR #15. `curate()` in `pipeline/api.py`; `python -m pipeline.test_api_parity` proves identical output (mutation-checked) |
| Document-type classifier, scored with near-copy families held out | PR #15. 55.9% vs 29.4% for guessing; `dashboard/public/doctype_eval.json`; `npm test` has 7 tests |
| Real NeMo Curator 1.3.0 comparison on the 35-PDF corpus | PR #16. NeMo removes 716 of 3,396 chunks, ours 71; `dashboard/public/nemo_comparison.json` |
| Improvement phases 0 to 4: healing wired in, newest-version dedup, PII precision rules, meaningful regulatory tags, classifier as an optional signal | PRs #7 to #13; `docs/IMPROVEMENT_LOG.md` |
| Tests | 10 Python self-check scripts and 7 dashboard tests, all passing on 20 Oct |

## In progress (owner, gate Wednesday 13:00 unless noted)

| Item | Owner |
|---|---|
| Run confirmed on Linux with all 35 PDFs; `requirements.txt` and `requirements-gpu.txt`; setup guide update | Aditi |
| `pipeline/device.py`: choose CUDA or CPU automatically, with a test that needs no GPU | Aditi |
| Demo laptop confirmed with a visible GPU (`nvidia-smi` inside Linux) | Kunal |
| Tests converted to pytest plus one end-to-end test; token statistics file; held-out quality review; GPU vs CPU timing on the RTX 4050 (Wed afternoon) | Kunal |
| Dashboard shows 35-document numbers from data; `pipeline/refresh_snapshots.py` and a "re-run pipeline" button; raw PII masked in the snapshot; panels for device, tokens and document types; demo script (Wed 18:00 to 21:00) | Saachi |
| Merge branches in order (Aditi, Kunal, Ankit, Saachi), final full run on `main`, `docs/FINAL_NUMBERS.md` for the slides | Ankit (Wed 13:00 to 18:00) |

## Not done, and why

- **OCR for scanned PDFs.** One PDF (`bank_of_baroda_aml_questionnaire.pdf`) is image-only and fails cleanly. Out of scope for the review.
- **GPU dedup.** NeMo's own dedup needs a CUDA GPU and cuDF (`docs/A1_3_dedup_gpu_finding.md`). Ours runs on the CPU.
- **Hosted API.** Deliberately not built: it needs a running server, and bank documents would have to leave the customer's machine. The library and terminal command run locally.
- **DeBERTa quality pass** (about 50 min on CPU). Not run; the classifier was rejected as a filter and stays an optional, off-by-default label.
- **Model fine-tuning.** Out of scope by design.

## Known issues (stated plainly)

- **Dashboard snapshots are stale until Saachi's refresh is merged.** `dashboard/public/pipeline_summary.json` and `curated.jsonl` still hold the old 18-document numbers. `nemo_comparison.json` and `doctype_eval.json` are current.
- **The document-type score is optimistic.** Four combinations were scored on the same 34 documents, and bank and NBFC policy were merged after seeing the confusion table. `fiu_reporting_spec` scores 0%.
- **The 649 chunks only NeMo removes have not been hand-checked.** Most come from two FIU report-format guides (repeated field descriptions).
- **Run time depends on machine load.** Full 35-PDF run on the CPU, three runs back to back on 21 Oct: `python -m pipeline.run` 379 s (CPU already 59% busy), `bfsi-curate` 326 s, `python -m pipeline.run` 330 s. The terminal command is as fast as the normal run; one earlier 16-minute run was a busy machine. Quote about 5.5 minutes on a quiet laptop.
- **Public contact details are redacted too.** Most of the 68 PII items are government emails and office PIN codes in public documents.
- **Tag keyword `fiu`** is counted inside FIU's own forms; left as is.

## Decisions made

| Date | Decision |
|---|---|
| 4 Oct | Lexical-diversity cutoff lowered from 0.30 to 0.20 after a fake-junk test and a full read of the alpha-ratio removals (`docs/IMPROVEMENT_LOG.md`) |
| 5 Oct | A chunk is tagged regulatory only with 2 distinct keywords (owner's choice) |
| 20 Oct | The pipeline is exposed as one function with a terminal command and the existing local API on top; no hosted server for the review |
| 21 Oct | Bank and NBFC policy merged into one document type, `institution_policy`; the merge is recorded as a variant tried |

## Fallbacks taken (history)

- Native Windows install of NeMo Curator fails (`fasttext`, `cosmos-xenna` need a C++ toolchain). Real NeMo runs on a Linux VM; `SETUP.md` documents the working setup.
- NVIDIA's DeBERTa quality classifier is about 17x stricter and judges layout, not quality (`docs/A1_4_quality_classifier_comparison.md`), so it is not used as a filter.
- Person-name detection uses a title cue and shape filter, trading recall for precision, after spaCy mislabelled legal phrases such as "Gazette Notification".
- Chunking is fixed at 180 words because PDF extraction does not keep blank-line paragraph breaks.
