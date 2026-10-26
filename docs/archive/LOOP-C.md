# LOOP C — Custom Validation: PII Extensions & Cross-Field Checks

**Read `CONTEXT.md` fully first — especially §2 (frozen contracts) and §4.**

**Owner scope:** extend PII detection and add validation logic that goes beyond
pattern-matching in isolation — the "validation" half of what TCS explicitly asked for.

**Files you own:** `pipeline/pii.py`. Stream A will eventually wrap real GLiNER-PII
around whatever's here — same coordination note as Stream B: land and stabilize your
rules before A's swap lands on this file.

**Git branch:** `stream-c-pii`

---

## THE GOAL (machine-decidable)

> At least one new PII entity type is detected beyond the current six (PAN, AADHAAR,
> EMAIL, PHONE, DATE, PINCODE, ACCOUNT_NUMBER, PERSON_NAME), AND at least one cross-field
> validation rule exists that catches something regex-in-isolation cannot, each verified
> with a real example from the actual corpus.

## CRITICAL RULE INHERITED FROM v1 — DO NOT VIOLATE

**PII redaction runs AFTER deduplication, never before.** This is non-negotiable and
already baked into the pipeline order. Any new validation logic you add must also
respect this — don't build something that needs to run before dedup.

## THE PRECISION LESSON — DON'T REGRESS IT

The existing PERSON_NAME detection had a real false-positive problem (dense legal text
made spaCy mistag "Gazette Notification" as a person). The fix was a personal-title-cue
requirement, trading recall for precision. **Any new entity type you add must go through
the same discipline: verify on the real corpus that it's not firing on false positives
before reporting it as working.** A redaction rule that flags things which aren't
actually PII is worse than not having the rule — it teaches nobody to trust the tool.

---

## TIERED ACCEPTANCE

### TIER 0 — MUST SHIP

**New entity type**

| # | Check |
|---|---|
| C0.1 | Pick ONE new entity type genuinely missing and relevant to KYC docs — candidates: GSTIN (15-char GST number), passport number format, voter ID (EPIC) format, CIN (Corporate Identity Number), IFSC code |
| C0.2 | Regex or detection logic implemented, following the existing `PATTERNS` list structure in `pii.py` |
| C0.3 | Verified on real corpus: at least 1 real true-positive example found and shown (before/after pair, same format as existing `pii_examples.json`) |
| C0.4 | Verified NOT over-firing: spot-check for false positives on the corpus before calling it done — document what you checked |

**Cross-field validation**

| # | Check |
|---|---|
| C0.5 | Implement at least one check that uses TWO detected fields together, not one in isolation — e.g., a detected PAN's structure (5 letters + 4 digits + 1 letter) partially encodes entity type in the 4th character; or flag when an ACCOUNT_NUMBER-shaped span appears with no nearby bank-context words (reduces false positives on generic long numbers that aren't actually account numbers) |
| C0.6 | This produces a distinguishable output — e.g., a `validation_flag` field on the chunk record marking "PII detected but context looks suspicious, human should verify" vs "PII detected with confident context" |
| C0.7 | Real example from the corpus showing the cross-field check catching something a single-pattern regex would have gotten wrong (either a false positive it suppresses, or new confidence info it adds) |

### TIER 1 — STRONGLY WANTED

| # | Check |
|---|---|
| C1.1 | A second new entity type, following the same C0.1-C0.4 discipline |
| C1.2 | Extend the existing name-detection precision approach (title-cue requirement) to a similarly precision-first design for the new entity types — document the same trade-off explicitly (this becomes a strong "here's our validation methodology" story for TCS) |
| C1.3 | Quantify precision improvement: if possible, show a rough before/after — "without the cross-field check, X spans would have been flagged; with it, only Y are, and we spot-checked that Y is all real" |

### TIER 2 — IF TIME ALLOWS

| # | Check |
|---|---|
| C2.1 | A structured validation report per document — not just per-entity redaction, but a document-level summary: "this document had N PII entities across M types, X flagged for manual review" |

---

## HARD RULES

1. **New fields only, additive to the chunk record** — never remove or rename existing
   fields (`chunk_id`, `doc_id`, `source_file`, `text`, `pii_redacted`).
2. **Every entity type addition needs a false-positive check documented**, not just a
   true-positive example. "It worked once" is not the same as "it doesn't over-fire."
3. **PII stage order stays fixed**: after dedup and quality filter, never before.
4. Do not touch the existing six entity types' regex without a clear reason and without
   re-verifying `pii_entities_redacted` counts don't regress on the real corpus.

## STOP CONDITIONS

- 3 attempts per entity-type detector before moving to a different candidate entity —
  some formats (e.g., passport numbers) may not appear in this specific 19-document
  corpus at all; if so, document that and pick a different one rather than forcing it.
- If genuinely no real example of a candidate entity type exists anywhere in the actual
  corpus, that's a valid reason to abandon that candidate — don't fabricate a document
  to test against; find a different entity type that's actually present.
