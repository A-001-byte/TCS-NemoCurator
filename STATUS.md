# Project Status

Last updated: Tuesday 27 Oct 2026, early morning. Review with TCS: Tuesday 27 Oct 2026, 10:30, in person.
The plan from "all tasks merged" to the release is `docs/FINALIZATION_LOOP.md`; every change with before/after numbers is in `docs/IMPROVEMENT_LOG.md`. All headline numbers are in `docs/FINAL_NUMBERS.md`, generated from the dashboard snapshots.

## Where we are

Phases 0 to 5 of the finalisation loop are done (PRs #23 to #28 merged), and the fresh-clone run on Linux (6.1) passed. Version 1.0.0 is prepared. What remains of phase 6: a rehearsal from a fresh clone by Kunal and Saachi, the GPU run on Ankit's RTX 3050, and the tags `v1.0.0` and `demo-ready` once `main` is green. Two decisions and two checks are still open; they are listed under "Not done".

## Done (with the evidence)

| Area | Evidence |
|---|---|
| 7-stage pipeline on 35 PDFs (34 readable), 3,325 final chunks, 68 PII items hidden, name detection on | `python -m pipeline.run`; README numbers table (generated); curated hash prefix `0c238547804a8407` (SHA-256 of `curated.jsonl`, the same on Windows and Linux since the line-ending fix; the earlier `8e2b6954e85ac3fd` was the same content with Windows line endings) |
| One code path for the library, the `bfsi-curate` command and the HTTP API | `curate()` in `pipeline/api.py`; `python -m pipeline.test_api_parity` proves identical output (mutation-checked) |
| HTTP API hardened: one error shape, correct statuses, limits, background refresh job | `tests/test_server_endpoints.py` (45 tests), `tests/test_refresh_job.py`; endpoint table in `README.md` |
| No silent degradation: name detection off is reported by the pipeline, the CLI and the dashboard | `tests/test_pipeline_edges.py`; this is what turned 68 into 66 on two machines |
| Dashboard: ten sections, document-type, token and device panels, refresh button that follows a background job, snapshots regenerated from a real run with PII example masking | `dashboard/`, `tests/test_refresh.py`; `npm run lint` 0 warnings, 14 `npm test` tests |
| Document-type classifier, scored with near-copy families held out | `dashboard/public/doctype_eval.json`; score and baseline in the README table |
| Real NeMo Curator 1.3.0 comparison on the same chunks | `dashboard/public/nemo_comparison.json`; `pipeline/nemo_compare.py` |
| Linux run matches the Windows run at every stage | `docs/team/evidence/linux_run.md` (Ubuntu 22.04 on WSL2) |
| GPU benchmark of the optional models, device chosen automatically | `docs/team/evidence/gpu_benchmark.md`, `pipeline/device.py` |
| Packaging: requirements split (core, ml, gpu, nemo, dev), real dependencies in `pyproject.toml`, `pip install .` gives a working `bfsi-curate` | `tests/test_packaging.py` (42 tests); clean-environment check in `docs/FINALIZATION_LOOP.md` item 4.1 |
| Quality gates: ruff check and format, CI on Ubuntu (three jobs), coverage 85.5% with an 80% floor | `.github/workflows/ci.yml`, `pyproject.toml` |
| Documentation: README (install, three ways to use it, API table, diagram), `SETUP.md` against the requirements files, generated numbers table, a test that every document link and file path exists | `tests/test_docs.py`, `tests/test_final_numbers.py` |
| Fresh-clone run on Linux (WSL2 and a VMware VM): install from the README, tests, full run, server, live upload through the API and the dashboard | 26 to 27 Oct. WSL2 (12 cores): tests 43 s, full run 4 min 18 s; same numbers and hash as Windows (`SETUP.md`, last section) |
| Optional GPU models behind CLI flags, run on an RTX 4050 | PR #29; stage counts unchanged, GLiNER reports 1,164 PII items against 68 for the default engine (it lacks our precision rules), so the headline stays 68 |
| Tests | 214 pytest tests, 11 `pipeline.test_*` self-check scripts, 14 dashboard tests; all pass |

## Not done, and why

- **Licence.** The owner has not chosen one (MIT, Apache-2.0 or all rights reserved), so none is added. `docs/FINALIZATION_LOOP.md` item 4.4 stays open for this.
- **The chunks only NeMo removes have not been hand-checked.** The side-by-side shows the counts; whether NeMo's extra removals are right or wrong has not been measured. It needs the Linux VM (loop item 5.4).
- **GPU deduplication.** NeMo's own dedup needs a CUDA GPU and cuDF (`docs/A1_3_dedup_gpu_finding.md`); cuDF runs on the RTX 4050 but the NeMo dedup import check has not passed. Ours runs on the CPU. Recorded as not done unless phase 6 closes it.
- **OCR for scanned PDFs.** One PDF (`bank_of_baroda_aml_questionnaire.pdf`) is image-only and fails cleanly. Out of scope.
- **Hosted service.** Deliberately not built: bank documents would have to leave the customer's machine. The library, the terminal command and a local API run on your own machine.
- **DeBERTa quality pass.** Not run on the corpus; the classifier was rejected as a filter and stays an optional, off-by-default label.
- **Model fine-tuning.** Out of scope by design.

## Known issues (stated plainly)

- **The document-type score is optimistic.** Four combinations were scored on the same 34 documents, and bank and NBFC policy were merged after seeing the confusion table. `fiu_reporting_spec` scores 0%.
- **The HTTP API has no authentication.** It listens on loopback by default and refuses nothing else; do not expose it on an untrusted network (`SECURITY.md`).
- **One run at a time.** A second `POST /api/run` while one is running answers 409.
- **Run time depends on the machine.** A full 35-PDF run on the CPU took 4 min 18 s in WSL2 on a 12-core laptop, about 5.5 minutes on a quiet Windows laptop, 11 to 12 minutes on a busy one, and **40 min 30 s inside a VMware VM** (6 virtual cores). Demonstrate on WSL2 or native Linux, not a VM. The terminal command is as fast as `python -m pipeline.run`.
- **Public contact details are redacted too.** Most of the PII items are government emails and office PIN codes printed in public documents.
- **The tag keyword `fiu`** is counted inside FIU's own forms; left as is.

## Decisions made

| Date | Decision |
|---|---|
| 4 Oct | Lexical-diversity cutoff lowered from 0.30 to 0.20 after a fake-junk test and a full read of the alpha-ratio removals (`docs/IMPROVEMENT_LOG.md`) |
| 5 Oct | A chunk is tagged regulatory only with 2 distinct keywords (owner's choice) |
| 20 Oct | The pipeline is exposed as one function with a terminal command and the existing local API on top; no hosted server for the review |
| 21 Oct | Bank and NBFC policy merged into one document type, `institution_policy`; the merge is recorded as a variant tried |
| 26 Oct | The finalisation loop changes no pipeline output; the documents and the dashboard read the same generated snapshots |

## Fallbacks taken (history)

- Native Windows install of NeMo Curator fails (`fasttext`, `cosmos-xenna` need a C++ toolchain). Real NeMo runs on a Linux VM; `SETUP.md` documents the working setup.
- NVIDIA's DeBERTa quality classifier is about 17x stricter and judges layout, not quality (`docs/A1_4_quality_classifier_comparison.md`), so it is not used as a filter.
- Person-name detection uses a title cue and shape filter, trading recall for precision, after spaCy mislabelled legal phrases such as "Gazette Notification".
- Chunking is fixed at 180 words because PDF extraction does not keep blank-line paragraph breaks.
