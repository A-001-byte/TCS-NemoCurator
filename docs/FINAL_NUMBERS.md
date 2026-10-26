# NemoCurator — Final Dashboard Numbers

## Current pipeline snapshot

| Metric | Result |
|---|---:|
| Input PDFs | 35 |
| Successfully extracted documents | 34 |
| Failed extractions | 1 |
| Final curated chunks | 3,325 |
| Detected PII entities redacted | 66 |
| Chunks with detected PII | 51 |
| Account numbers suppressed | 5 |
| Furniture lines removed during healing | 3,176 |
| Chunks removed during deduplication | 330 |
| Chunks removed by quality filtering | 71 |

## Document-type classification and clause similarity

- Documents scored: 34
- Document-level accuracy: 61.76%
- Family-level accuracy: 55.88%
- Majority baseline: 29.41%
- Confident predictions: 18
- Flagged low-confidence predictions: 16

This is document-type classification and clause similarity, not a trained fraud/anomaly model.

## Limitations

- One input PDF, `bank_of_baroda_aml_questionnaire.pdf`, failed extraction because its extraction was empty.
- PII detection uses regex and spaCy. Name detection is unavailable, so complete PII detection is not guaranteed.
- `token_stats.json` is absent; the token statistics panel should remain hidden when the file is unavailable.
- The current metrics describe the existing snapshot and should be regenerated before claiming newer results.
