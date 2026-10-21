# Linux Run — Aditi

**Date:** 20 Oct 2026
**OS:** Kali Linux via WSL2
**Python version:** Python 3.11.0rc1
**Venv:** venv-curator

## Commands run

source venv-curator/bin/activate
python3 -m pipeline.run


## Stage numbers — match confirmed

| Stage | Expected (Windows run) | This run (Kali) | Match? |
|---|---|---|---|
| PDFs in | 35 | 35 | ✅ |
| PDFs readable | 34 | 34 | ✅ |
| Chunks into dedup | 3,726 | 3,726 | ✅ |
| Chunks after dedup | 3,396 | 3,396 | ✅ |
| Final chunks | 3,325 | 3,325 | ✅ |
| PII items redacted | 68 | 68 | ✅ |

## Notes
- Exact match on every stage — no discrepancy to explain.
- One extraction failure as expected: `bank_of_baroda_aml_questionnaire.pdf` (scanned PDF, no extractable text — known limitation, OCR out of scope).
- Environment differs from SETUP.md (Kali native vs. WSL2 Ubuntu 22.04) but produced identical results.


