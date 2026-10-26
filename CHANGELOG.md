# Changelog

All notable changes to this project. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Numbers in parentheses are pull requests. Before-and-after figures for each pipeline change are in
`docs/IMPROVEMENT_LOG.md`.

## [Unreleased] (towards 1.0.0)

### Added
- One entry point for the pipeline: `curate()` in `pipeline/api.py`, the `bfsi-curate` command (`run`, `serve`,
  `--version`) and the local HTTP API all share one code path; a test checks they return identical output (#15, #25).
- Document-type classifier (nearest centroid on TF-IDF) scored with each document's near-copy family held out, with its
  caveats stated in the output (#15).
- Dashboard: Document types and Token statistics panels, a Device pill, a refresh button that follows a background
  job, and an alert when person-name detection is off (#20, #22, #24, #25).
- 16 more public source documents (19 to 35 PDFs), kept as a never-tuned-on test of the earlier rules (#14).
- Automatic CPU/GPU selection for the optional models, with a measured GPU benchmark (#18, #19).
- Token statistics, pytest suite with an end-to-end test, a held-out quality review (#19).
- A real NVIDIA NeMo Curator 1.3.0 comparison on the 35-PDF corpus (#16).
- CI (lint, format check, tests with coverage, package smoke test, dashboard checks), requirements split into core,
  `ml`, `gpu`, `nemo` and `dev`, a packaging consistency test, `CONTRIBUTING.md`, `SECURITY.md`, a pull-request
  template and this changelog.
- `scripts/make_final_numbers.py`: `docs/FINAL_NUMBERS.md` is generated from the snapshots (#24). It now also writes
  the README's numbers table, and `--check` reports a stale file; a test fails when either is out of date.
- A test that every link and file path in the documents exists (`tests/test_docs.py`).
- API reference table, architecture diagram and configuration table in the README.

### Changed
- Page-splice healing runs inside the main pipeline, before dedup (#8).
- Dedup keeps the newest version of a policy (#10).
- The lexical-diversity cutoff is 0.20, down from 0.30, after reading what it removed (#9).
- PII rules check context: dates only after a birth cue, PIN codes only in an address context, Aadhaar by checksum,
  SWIFT only with a label, and digits inside numeric tables or placeholders are left alone (#11, #14).
- Regulatory tags use a pruned keyword list and need 2 distinct keywords (#13).
- NVIDIA's quality classifier is an optional, off-by-default label and never removes a chunk (#13).
- The repository root holds only what a visitor needs; planning papers moved to `docs/archive/`; the dashboard's
  1,504-line `App.jsx` is split into one file per section (#26).
- `requires-python` is `>=3.11`, the version everything is tested on.
- `SETUP.md` rewritten around the split requirements files (install, GPU, NeMo, troubleshooting); the README's typed
  numbers are replaced by the generated table.

### Fixed
- `curated.jsonl` and `pipeline_summary.json` were written with Windows line endings on Windows, so the same input gave a different
  file hash on each operating system. Both are now written with Unix line endings everywhere.
- Uploaded or listed PDFs with an upper-case extension (`REPORT.PDF`) were skipped on Linux; folders named `x.pdf` were
  counted as inputs (#25).
- A spaCy load failure silently turned person-name detection off (68 PII items became 66). It is now reported
  everywhere (#25).
- The published snapshot contained a local `C:\Users\...` path, and its curated text had public fax numbers rewritten as
  `[AADHAAR REDACTED]` (#24).
- The refresh request blocked for minutes and could be triggered by a plain GET (#24).
- Malformed API requests (bad `Content-Length`, a body of `null`, non-object items, duplicate names) could drop the
  connection; every failure now returns `{"error": ...}` with a fitting status (#25).
- Seven false PII alarms found on the new documents: digits in statistics tables and `0000000000` placeholders (#14).
