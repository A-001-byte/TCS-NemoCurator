# LOOP D — Dashboard Extension & Pattern-Matching Scenario

**Read `CONTEXT.md` fully first — especially §2 (frozen contracts) and §4.**

**Owner scope:** two parts. First, extend the existing React dashboard to surface
whatever B and C build. Second — and this is the part with real upside — start building
toward the actual end goal TCS described: new KYC data coming in, matched against
learned patterns.

**Files you own:** `dashboard/` (all of it), plus a new `pattern/` module at repo root
for the pattern-matching groundwork. **You do not touch pipeline/ at all.** You build
against a FROZEN snapshot of `curated.jsonl` and `pipeline_summary.json` — copy them out
on day one, before A/B/C start changing the pipeline, so you're never blocked waiting
for their work to land.

**Git branch:** `stream-d-dashboard`

---

## THE GOAL (machine-decidable)

> The dashboard displays whatever new fields/rules B and C produce (once their schemas
> are shared, even before their code lands — build against CONTEXT.md's contracts plus
> whatever additive fields they document), AND a first working prototype exists that
> takes one new "incoming KYC document" and classifies/scores it against patterns learned
> from the existing curated corpus.

## WHY THIS IS THE MOST IMPORTANT STREAM FOR THE REAL GOAL

Everything else (A, B, C) is data preparation. This is the first piece of what TCS
actually wants to end up with — a model that recognizes patterns in new KYC data. Even a
rough first version here is more valuable to the final pitch than a perfect curation
pipeline, because it's the part that isn't just "cleaning," it's the actual product.

---

## PART 1 — DASHBOARD EXTENSION (lower priority, do this first because it's fast)

### TIER 0 — MUST SHIP

| # | Check |
|---|---|
| D0.1 | Dashboard has a placeholder section/tab ready for "custom filtration rules" (Stream B's output) — even before B's code lands, build the UI against CONTEXT.md's documented additive fields |
| D0.2 | Dashboard has a placeholder section/tab ready for extended PII/validation (Stream C's output) — same approach |
| D0.3 | Existing T0.7-T0.10 functionality (from v1) still works: `npm run build` exits 0, funnel view, PII before/after, per-doc drill-down all still render correctly |

### TIER 1

| # | Check |
|---|---|
| D1.1 | Once B/C land real fields, wire them into the placeholders for real (not just UI shells) |
| D1.2 | Add a stage-comparison view if Stream A produces the equivalent-logic vs real-Curator diff (A1.4) — this is a genuinely interesting visual: "here's what the real classifier caught that ours missed" |

---

## PART 2 — PATTERN-MATCHING SCENARIO (higher priority, this is the real deliverable)

### TIER 0 — MUST SHIP

| # | Check |
|---|---|
| D0.4 | Define concretely what "pattern" means here — pick ONE narrow, well-defined scenario rather than a vague general one. Candidate: "does this new document's structure/content resemble a known KYC-policy document type (e.g., matches the shape of an AML/CFT policy vs a customer-facing KYC form vs a regulatory circular)?" — narrow and testable beats broad and hand-wavy |
| D0.5 | Build a simple similarity/classification approach against the EXISTING 19-document corpus as the "known patterns" reference set — start simple: TF-IDF + cosine similarity, or embedding similarity if time allows, not a trained neural classifier (no time for that in 2-3 weeks alongside everything else) |
| D0.6 | Take ONE new, real, held-out KYC/regulatory document (not from the original 19) and run it through: does the system correctly identify which existing document type it's most similar to? |
| D0.7 | Report a similarity score or confidence number, not just a binary yes/no — TCS's ask was about recognizing patterns, and a score is more honest about uncertainty than a hard classification |

### TIER 1 — STRONGLY WANTED

| # | Check |
|---|---|
| D1.3 | Test on 2-3 held-out documents, not just one — a single test case proves nothing, several gives a real signal of whether the approach works |
| D1.4 | Document what "learned patterns" means precisely in a short write-up — e.g., "we're using term-frequency patterns from the curated corpus, not a trained ML model" — so nobody overclaims this as more sophisticated than it is |
| D1.5 | Surface this in the dashboard as a simple demo: paste/select a new document, see the similarity result |

### TIER 2 — IF TIME ALLOWS

| # | Check |
|---|---|
| D2.1 | Extend beyond document-type classification toward something closer to anomaly detection — e.g., does a new document contain a clause structure NOT seen in the existing corpus, which might indicate something worth flagging |

---

## HARD RULES

1. **Never touch pipeline/** — if you need a pipeline change, ask A/B/C, don't do it
   yourself; you'd be editing files outside your ownership and risking merge conflicts
   with people actively working there.
2. **Be explicit about what the pattern-matching approach actually is.** TF-IDF
   similarity is not "AI understanding KYC patterns" — say what it really is. Overclaiming
   here is the single easiest way to lose credibility with TCS if they ask a follow-up
   technical question.
3. **One narrow, well-defined pattern-matching scenario beats a vague ambitious one.**
   D0.4 exists specifically to force this decision early — don't skip it and start
   coding before the scope is nailed down in one sentence.
4. Use the frozen `curated.jsonl` snapshot from day one. If you need it refreshed later
   (once A/B/C's changes land), that's a deliberate, communicated step — not something
   that happens silently because you re-ran the pipeline yourself.

## STOP CONDITIONS

- If D0.4 (defining the scenario) isn't nailed down in the first 2-3 days, escalate to
  the team — this is a decision, not an engineering task, and it blocks everything else
  in Part 2.
- 3 attempts on any one similarity approach before trying a simpler one — if embedding
  similarity is fighting you, fall back to TF-IDF; a working simple approach beats a
  broken sophisticated one.
