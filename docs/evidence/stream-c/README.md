# Stream C evidence (Ankit)

Snapshot of a full pipeline run, copied here on purpose; pipeline runs never write
to docs/. Produced from commit `2f284f8` (main + Stream B + Stream C) on 2026-09-23.

| File | What it shows |
|---|---|
| `pii_stage_record.json` | Entity counts incl. CIN, SWIFT/BIC; account numbers suppressed by cross-field validation |
| `validation_report.json` | Per-document PII exposure, most-exposed first |
| `heal_stage_record.json` / `heal_report.json` | Page-Splice Healing before/after purity metrics, every removed furniture signature, every OCR repair |
| `regulatory_changelog.json` | Sentence-level diff between versions of the same policy, split into substantive vs cosmetic |

`pii_examples.json` is deliberately not copied: it stores raw pre-redaction values.

Regenerate: `python -m pipeline.run && python -m pipeline.heal && python -m pipeline.changelog`
