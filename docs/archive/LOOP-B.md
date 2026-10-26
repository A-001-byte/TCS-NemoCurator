# LOOP B — Custom Filtration: Quality & Deduplication

**Read `CONTEXT.md` fully first — especially §2 (frozen contracts) and §4.**

**Owner scope:** exactly what TCS asked for — "custom filtration, validation,
deduplication, anything, alongside Curator." Build domain-specific rules that go beyond
generic text-quality hygiene, layered on top of (not replacing) the existing pipeline.

**Files you own:** `pipeline/quality.py`, `pipeline/dedup.py`. Stream A will eventually
touch these files' internals to swap in real Curator calls — coordinate timing so your
custom rules land and stabilize BEFORE Stream A's swap, so A can wrap real Curator calls
around your rules rather than the other way around.

**Git branch:** `stream-b-filters`

---

## THE GOAL (machine-decidable)

> At least two new custom filtration rules exist, each demonstrably domain-specific (not
> generic NLP hygiene copied from a tutorial), each with a real before/after example on
> the actual 19-document corpus, each emitting a stage record matching CONTEXT.md
> Contract 3.

## WHY THIS MATTERS MOST TO TCS RIGHT NOW

He said this to multiple groups — it's clearly his top ask. This is the stream most
likely to directly influence whether TCS extends the engagement.

---

## TIERED ACCEPTANCE

### TIER 0 — MUST SHIP

**Rule 1 — Regulatory-keyword routing (quality.py)**

| # | Check |
|---|---|
| B0.1 | A keyword list exists for BFSI/regulatory terms: KYC, AML, STR, SAR, UBO, PEP, CDD, EDD, sanctions, beneficial owner, etc. |
| B0.2 | Each surviving chunk gets tagged with whether it matches ≥1 regulatory keyword — this is a NEW field, added to the chunk record, not a replacement for existing fields (contract-safe: additive only) |
| B0.3 | Stage record reports how many chunks were keyword-tagged vs not, on the real corpus |
| B0.4 | At least 3 real example chunks shown: one clearly regulatory-tagged, one clearly not, one borderline — demonstrates the rule actually discriminates, not just tags everything |

**Rule 2 — Regulatory-boilerplate-aware dedup (dedup.py)**

| # | Check |
|---|---|
| B0.5 | Distinguish "boilerplate duplicate" (same definitions/disclaimer clause appearing across MULTIPLE DIFFERENT bank documents) from "generic near-duplicate" (repeated content within the same document) — these are different phenomena with different implications |
| B0.6 | Stage record breaks down `fuzzy_duplicate` into these two sub-categories instead of one undifferentiated number |
| B0.7 | At least 2 real examples of cross-document boilerplate found in the actual corpus (e.g., the same RBI definition clause appearing in two different bank policy PDFs) |

### TIER 1 — STRONGLY WANTED

| # | Check |
|---|---|
| B1.1 | A third custom rule: chunk-level "regulatory density score" — what fraction of a chunk's content is regulatory-keyword-bearing vs generic prose, useful signal for later pattern-matching work (Stream D) |
| B1.2 | Tunable thresholds for all new rules pulled into named constants at the top of the file (not magic numbers buried in logic) — matches the existing codebase's style |
| B1.3 | A short write-up (in this file's STATUS section or a docstring) explaining WHY each rule exists and what specific problem in the real corpus it addresses — this is what makes it "custom" rather than generic, and it's what you'll say out loud to TCS |

### TIER 2 — IF TIME ALLOWS

| # | Check |
|---|---|
| B2.1 | Configurable rule set — rules can be toggled on/off via a config file, useful once Stream A wraps real Curator around this |

---

## HARD RULES

1. **New fields only, never remove or rename existing chunk-record fields** — Stream D
   is building against the current schema and will break silently if you change it.
2. **Every custom rule needs a real example from the actual 19-document corpus.**
   A rule that's never been shown to fire on real data isn't verified, per LOOP
   philosophy inherited from v1 — don't report a rule as done without one.
3. **Don't just port over generic "quality filter" tricks from NLP tutorials** (stopword
   ratio, perplexity, etc.) and call them custom — TCS's ask was specifically for rules
   that make sense FOR THIS DOMAIN. If you can't explain in one sentence why a rule is
   BFSI/regulatory-specific rather than generic text hygiene, it doesn't count toward
   B0.1-B0.7.

## STOP CONDITIONS

- 3 attempts per rule design before escalating for a second opinion from the team —
  don't burn a week perfecting one rule's threshold.
- If B0.1-B0.7 (Tier 0) isn't green by roughly the halfway point of the 2-3 week window,
  stop adding new rules and make what exists rock-solid with real examples ready to show.
