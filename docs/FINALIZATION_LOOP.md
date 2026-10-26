# Finalisation Loop: from "all tasks merged" to a production-grade release

Started Monday 26 Oct 2026, 21:40. Review with TCS: Tuesday 27 Oct 2026, 10:30. After this loop, the project is run by hand on Linux (phase 6).

Phases are ordered by **demo impact first, tidiness second**, so that if time runs out the demo still works.

## The loop (one iteration per task)

1. **SELECT** the first unchecked task in the lowest open phase.
2. **VERIFY the premise.** Read the current code or run the command that shows the problem. If it is not a real problem any more, tick it with "not needed: reason".
3. **CHANGE** the smallest thing that fixes it. Behaviour rules get a test that fails when the rule is broken (checked by temporarily breaking it).
4. **CHECK.** The task's own check, then the fast suite: `python -m pytest -q`, `cd dashboard && npm test && npm run lint && npm run build`.
5. **COMMIT**, one task per commit, `type: what changed`.
6. **LOG.** Tick the box below and add the evidence (command and result) in one line.
7. At the end of a phase: **PUSH the phase branch, open a PR, STOP** until it is merged. The next phase starts from the updated `main`.

**Stop and ask** when a task needs a decision, a destructive step (deleting tracked files, history changes), anything outside this repository, or fails twice. Never push to `main`, never force-push, never fake a check, never change a number without regenerating it.

## Decisions (defaults apply unless changed)

| # | Decision | Default |
|---|---|---|
| D1 | Licence | **Ask the owner.** Nothing is added until chosen (options: MIT, Apache-2.0, "all rights reserved") |
| D2 | Old planning files at the repo root (`LOOP*.md`, `CONTEXT.md`, `NEW CONTEXT.md`, blueprint PDF, `quality_comparison_log.txt`, `logs/`) | **Move** to `docs/archive/`, not delete |
| D3 | Regulatory tag threshold (2 distinct keywords) | Keep; documented as a trade-off (Kunal found 17 of 20 untagged RBI chunks substantive) |
| D4 | OCR for scanned PDFs, a hosted API, model training | Out of scope; stated in the README |

## Phase 0: baseline (before any change)

- [x] 0.1 `main` is current; `pytest` 29 pass, `npm test` 7 pass, `npm run lint` clean or listed, `npm run build` ok — 29 pytest, 7 npm test, build ok, one known lint warning (26 Oct)
- [x] 0.2 Full run on `main`: 3,325 chunks, 68 PII (names on), timing recorded — 3,325 chunks, 68 PII, names on, 11 min 48 s on a busy laptop (26 Oct)
- [x] 0.3 Open the PR for Aditi's `feat/aditi-final-evidence` (docs only) — PR #23

## Phase 1: demo-critical (what the audience sees)

- [x] 1.1 PII example masking: keep `doc_id` and the already-redacted context, mask only the original value; add `pipeline/test_refresh.py` (7 stages, no raw email, 10-digit or Aadhaar-shaped string in any snapshot, numbers equal the pipeline's) — `pipeline/refresh_snapshots.py`; `tests/test_refresh.py` (7 tests, 6 rules mutation-checked); also fixed a local-path leak in the committed snapshot
- [x] 1.2 Regenerate every dashboard snapshot from `main` (expect 68 PII, names on, `device` present); no byte-order marks; stop committing regenerated copies of other people's files by hand — real refresh on 35 PDFs: 3,325 / 68 / names on / device cpu, curated hash 8e2b6954e85ac3fd unchanged, no byte-order mark, no local path
- [x] 1.3 Dashboard panels: **Document types** (caption read from `doctype_eval.json`), **Tokens** (`token_stats.json`), **Device** badge; each hides itself if its file is missing — `dashboard/src/sections/`, `shapes.js`, `useSnapshot.js`; checked in a browser; npm test 14 pass
- [x] 1.4 Refresh without a frozen button: `POST /api/refresh` starts a background job and answers 202; `GET /api/refresh/status`; a second request while running answers 409; the button polls — `pipeline/refresh_job.py`; `tests/test_refresh_job.py` (4 tests, 5 mutations); browser: running, success, server down
- [x] 1.5 Demo script and likely questions rewritten for Linux and for the real numbers, with the live 3-PDF sample, the NeMo comparison, the document-type caveat and the terminal command — `docs/demo/DEMO_SCRIPT.md` and `docs/demo/LIKELY_QUESTIONS.md`
- [x] 1.6 `scripts/make_final_numbers.py` builds `docs/FINAL_NUMBERS.md` from the snapshots, so slides, README and dashboard cannot disagree — `scripts/make_final_numbers.py`; `tests/test_final_numbers.py` (7 tests); `docs/FINAL_NUMBERS.md` generated

## Phase 2: backend hardening (the API and the library)

- [x] 2.1 Server: `logging` instead of `print`, host and port from environment or flags, one error shape for every failure, 405 for wrong methods, clean shutdown, `bfsi-curate serve` — `pipeline/server.py` rewritten; real process checked with curl (200, 405 + Allow, 400 JSON errors, structured log); `bfsi-curate serve`
- [x] 2.2 Endpoint tests: `/api/health`, `/api/run` (bad JSON, not a PDF, too large, too many files, success), `/api/refresh` (accepted, busy, status) — `tests/test_server_endpoints.py` (45 tests, 8 rules mutation-checked), `tests/test_refresh_job.py` (4)
- [x] 2.3 **No silent degradation:** if spaCy or its model cannot load, the stage record, the CLI and the dashboard say "name detection off" (this is what turned 68 into 66 on two machines) — `pii.py` keeps the reason, `run.py` summary carries `name_detection_error`, CLI warns on stderr, dashboard shows an alert; tests in `tests/test_pipeline_edges.py` (11 tests, 7 mutations)
- [x] 2.4 Library hygiene: no stray `print` in importable code, type hints on public functions, `bfsi-curate --version`, clear exit codes documented — `--version`, `--verbose`, exit codes 0/1/2/130 documented and tested (`tests/test_cli.py`, 15 tests); `pipeline/__init__.py` holds the version
- [x] 2.5 `curate()` input checks match the server's (only real PDFs, size limits) — `extract.list_pdfs` (any-case extension, regular files only) used by `curate()` and the extract stage; busy lock and clear stop reason shared by library, CLI and API

## Phase 3: repository hygiene and structure

- [ ] 3.1 Root cleanup per D2; `DEMO_SCRIPT.md` and `LIKELY_QUESTIONS.md` move to `docs/demo/`; every reference updated
- [ ] 3.2 `.gitattributes` (LF), `.editorconfig`, `.gitignore` audit, remove byte-order marks, stop the CRLF warnings
- [ ] 3.3 Split `dashboard/src/App.jsx` (1,473 lines) into one file per section, none over 400 lines; fix the `oxlint` warning
- [ ] 3.4 Dead code and unused imports removed (found by `ruff`)
- [ ] 3.5 `docs/README.md` index so every document is findable

## Phase 4: quality gates, packaging, CI

- [ ] 4.1 Requirements split into core, NeMo (`nemo_compare` only), GPU and dev; `pyproject.toml` dependencies and extras from them; `pip install .` works in a clean virtualenv and `bfsi-curate --version` runs
- [ ] 4.2 `ruff` config; lint and format check pass
- [ ] 4.3 GitHub Actions: Python tests, and dashboard lint, test and build; status badge in the README
- [ ] 4.4 `CONTRIBUTING.md`, `CHANGELOG.md`, PR template, a short PII and security note; licence per D1
- [ ] 4.5 Coverage measured for `pipeline/` and the number stated as measured

## Phase 5: documentation and evidence

- [ ] 5.1 README final: install, three ways to use it, **API reference table**, architecture diagram, numbers from `FINAL_NUMBERS.md`
- [ ] 5.2 `STATUS.md` final; progress report merged; `IMPROVEMENT_LOG.md` closing entry
- [ ] 5.3 `SETUP.md`: Aditi's verified Linux install merged and consistent with the requirements files
- [ ] 5.4 *(needs the VM)* hand-check a sample of the 649 chunks only NeMo removes and state the measured rate

## Phase 6: release and manual Linux run (done together, step by step)

- [ ] 6.1 Fresh clone on Linux; install exactly as the README says; tests; CLI; server; dashboard; live upload; timing
- [ ] 6.2 GPU path on the RTX laptop: device badge shows the GPU, optional-model benchmark reproduced; NeMo GPU dedup import check (Aditi's open B4) either passes or is recorded as not done
- [ ] 6.3 Rehearsal twice from a fresh clone (Kunal and Saachi); tag `v1.0.0` and `demo-ready`; release notes

## Pull request plan

One branch and one PR per phase (`final/p1-demo-critical`, `final/p2-backend`, `final/p3-hygiene`, `final/p4-quality-gates`, `final/p5-docs`), each started from the updated `main`.
