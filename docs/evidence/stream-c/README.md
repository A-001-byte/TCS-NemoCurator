# Stream C evidence (Ankit)

Snapshot of a full pipeline run, copied here on purpose; pipeline runs never write
to docs/. Produced from commit `3cef5c8` (branch `fix/p3-pii-rules`: healing in the pipeline,
newest-version dedup, Phase 3 PII rules) on 2026-10-04. Previously `2f284f8` on 2026-09-23;
`heal_*` and `regulatory_changelog.json` came out identical, `pii_stage_record.json` and
`validation_report.json` changed (PII entities 284 -> 43, address PIN codes 241 -> 6).

| File | What it shows |
|---|---|
| `pii_stage_record.json` | Entity counts incl. CIN, SWIFT/BIC; candidates rejected by context (account numbers, SWIFT, dates, PIN codes, Aadhaar) |
| `validation_report.json` | Per-document PII exposure, most-exposed first |
| `heal_stage_record.json` / `heal_report.json` | Page-Splice Healing before/after purity metrics, every removed furniture signature, every OCR repair |
| `regulatory_changelog.json` | Sentence-level diff between versions of the same policy, split into substantive vs cosmetic |

`pii_examples.json` is deliberately not copied: it stores raw pre-redaction values.

Regenerate: `python -m pipeline.run && python -m pipeline.heal && python -m pipeline.changelog`
