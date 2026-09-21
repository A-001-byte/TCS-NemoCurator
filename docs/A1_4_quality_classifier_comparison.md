# A1.4 — Quality Filter Comparison: Heuristic vs. Real nvidia/quality-classifier-deberta

## Setup
- 2247 deduped chunks from all 18 successfully-extracted PDFs, run through both:
  - Existing heuristic (word count, alpha ratio, symbol ratio, lexical diversity)
  - Real nvidia/quality-classifier-deberta, invoked directly via `transformers`
    (NOT via Curator's ProcessingStage/DistributedDataClassifier — that path
    requires GPU per NVIDIA's own docs, unavailable on this dev machine.
    Same model weights, same real inference, different invocation path.)
- "Low" classifier output mapped to removal; "Medium"/"High" mapped to pass.
  This threshold choice is ours, not the model's — worth revisiting.

## Headline finding
| Metric | Heuristic | Real classifier |
|---|---|---|
| Removed | 58 / 2247 (2.6%) | 1020 / 2247 (45.4%) |

The real classifier is ~17x stricter than our heuristic. This is NOT random
noise — it correlates directly with document structure.

## Document-level pattern
Form/questionnaire-structured documents get flagged Low at very high rates:
- fiu_india_reporting_format: 97% (617/635)
- bank_of_baroda_kyc: 100% (8/8, small sample)

Prose-structured documents (circulars, master directions) mostly pass:
- rbi_fraud_master_direction_elp: 0% (0/12)
- bhiwani_dccb_kyc_aml_cft_2023_24: 7% (14/201)
- fiu_india_aml_cft_guidelines_2023: 8% (2/24)

## Why this happens
quality-classifier-deberta is trained on Common Crawl to judge general web-text
fluency/coherence. It has no domain awareness of BFSI regulatory content. A
KYC questionnaire's terse, form-field language (checkboxes, tabular fields,
short fragmented lines from PDF extraction) reads as "low quality" to a
fluency classifier even when it's completely valid, useful regulatory content.

## Implication — flagging this plainly, not softening it
Wiring the real classifier in as a direct drop-in replacement would shrink
the curated corpus from 2189 to ~1227 chunks (-44%), disproportionately
removing form/questionnaire content — exactly the kind of structured
compliance artifact (FIU-IND reporting formats, bank questionnaires) that's
likely valuable for the anomaly/pattern-recognition end goal TCS described.

This is not a case where "the real model is just better." It's a case where
a general-purpose quality classifier is a poor fit for this specific
document type, applied naively. Recommend NOT using it as a hard filter
as-is. Options worth team discussion:
1. Use classifier output as an additional SIGNAL/metadata field (like
   Stream B's regulatory_density_score) rather than an automatic removal.
2. Apply it only to prose-heavy document types, skip it for
   form/questionnaire-structured ones.
3. Keep the heuristic as primary filter; treat classifier disagreement as
   a review flag for human spot-checking, not automatic action.

## Raw data
Full per-chunk comparison: data/quality_comparison.json (2247 records)
