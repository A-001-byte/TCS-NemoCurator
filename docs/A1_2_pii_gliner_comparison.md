# A1.2 — GLiNER-PII vs. Current Pipeline (regex + spaCy + cross-field validation)

## Setup
Real nvidia/gliner-PII, invoked directly via the `gliner` library (CPU),
tested against 249 chunks the current pipeline already flagged as
containing PII, sampled across multiple documents. Full 2189-chunk
comparison was started but does not complete within this work session
(~8.5s/chunk, ~5hr total) -- findings below are from the completed
249-chunk sample, a real and substantial dataset, not a full census.

Note: this sample was drawn from an earlier pipeline run than the one
reflected in the current `pipeline_summary.json` (`chunks_with_pii: 248`).
The corpus and PII logic have both been extended since (CIN, SWIFT_BIC,
cross-field account validation), so a like-for-like re-sample against the
current run is needed before treating the 249 figure as reproducible
against today's `main`.

## Finding 1 -- PERSON_NAME: real model is significantly noisier
GLiNER fires PERSON_NAME on job titles and role references with no
name-shaped span: "Managing Director", "Joint Secretary (IS.I)",
"UAPA nodal officer", "Branch Manager", list markers in enumerated
official lists. Confirmed in 30+ of the 249 sampled chunks. This is
exactly the failure mode Stream C's title-cue-gated spaCy approach was
built to prevent (see pii.py module docstring) -- and that guard is
working: the current pipeline's real PERSON_NAME count across the whole
corpus was 1. GLiNER, run with no equivalent precision guard, fires far
more often on this document type (dense regulatory/official lists).

## Finding 2 -- PHONE/EMAIL: real model performs well, unexpectedly
GLiNER correctly distinguished fax/phone numbers from bank account
numbers in every sampled case (e.g. "Fax No. 011-23092551" -> PHONE,
not ACCOUNT_NUMBER) without needing Stream C's hand-built telecom-context
suppression logic. This suggests the zero-shot model may not need the
same cross-field guard for this specific distinction, though this needs
confirming at full-corpus scale before relying on it.

## Not yet tested
- Full corpus (2189 chunks) -- comparison script written and can be
  re-run to completion outside this time-boxed session
- Whether GLiNER catches anything the current pipeline MISSED entirely
  (false negatives), not just what it disagrees on
- CIN/SWIFT_BIC categories specifically (present in label map, not yet
  seen fire in the sample)

## Recommendation
Do not swap PERSON_NAME detection to raw GLiNER without adding an
equivalent precision guard (title-cue or similar) -- would regress a
real, working precision fix. PHONE/EMAIL detection looks like a
promising real-model candidate pending full-corpus confirmation.
