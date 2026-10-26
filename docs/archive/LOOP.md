# LOOP SPEC — Overnight Build

**Prerequisite:** read `CONTEXT.md` fully before starting. This document assumes it.

**Time budget:** ONE EVENING. The showcase is tomorrow.

---

## 0. THE GOAL (machine-decidable)

> Produce a running demo where **real Indian RBI/KYC regulatory PDFs** are processed through a multi-stage curation pipeline and the results — including visibly redacted PII and removed duplicates — are displayed in a **React dashboard**, with fine-tuning-ready JSONL written to disk.

**The loop is DONE when every check in Tier 0 passes.** Not when it feels finished.

---

## 1. TIERED ACCEPTANCE

Build strictly in order. Do not start a tier until the previous one fully passes.

### TIER 0 — MUST SHIP (if only this exists, the demo still works)

| # | Check | How to verify |
|---|---|---|
| T0.1 | ≥15 real RBI/bank KYC PDFs downloaded | `ls data/raw/*.pdf \| wc -l` returns ≥15 |
| T0.2 | Text extracted from every PDF, no crashes | `python -m pipeline.extract` exits 0; `ls data/extracted/*.txt \| wc -l` equals PDF count |
| T0.3 | Pipeline runs end to end without error | `python -m pipeline.run` exits 0 |
| T0.4 | Deduplication removes >0 documents/chunks | Run output reports `duplicates_removed > 0` |
| T0.5 | PII redaction fires on ≥1 real detection | Run output reports `pii_entities_redacted > 0`; a before/after pair is printed |
| T0.6 | Fine-tuning-ready JSONL written | `data/output/curated.jsonl` exists, every line is valid JSON, has `text` field |
| T0.7 | React dashboard builds and runs | `npm run build` exits 0; dev server serves without console errors |
| T0.8 | Dashboard shows per-stage counts (in → out per stage) | Visible on screen, numbers match pipeline output JSON |
| T0.9 | Dashboard shows a real before/after PII redaction example | Visible on screen, text is from an actual processed document |
| T0.10 | `README.md` states exactly what is real vs simulated | File exists and contains an explicit "What is real / What is not" section |

### TIER 1 — STRONGLY WANTED

| # | Check |
|---|---|
| T1.1 | Actual `nemo-curator` installed (`pip show nemo-curator` succeeds) |
| T1.2 | At least one pipeline stage genuinely executed via the NeMo Curator 1.x API (`ProcessingStage` → `Pipeline` → executor) |
| T1.3 | Dashboard labels clearly which stages are real-Curator vs equivalent-logic |
| T1.4 | Document-level drill-down in dashboard: click a doc, see its stage-by-stage journey |

### TIER 2 — ONLY IF TIER 0 AND 1 ARE FULLY GREEN

| # | Check |
|---|---|
| T2.1 | Narrative drafter page exists in the React app |
| T2.2 | Pasting structured case facts returns a draft STR narrative |
| T2.3 | The draft is visibly grounded in retrieved text from the curated corpus (show the retrieved chunks) |
| T2.4 | UI states plainly "no fine-tuning — off-the-shelf model + retrieval over curated corpus" |

---

## 2. HARD RULES FOR THE LOOP

1. **Never fake a passing check.** If T0.5 can't fire because PII detection isn't working, the check FAILS. Do not print a hardcoded number. Do not use a placeholder document with planted fake PII and call it real. A failing check honestly reported is fine; a faked one destroys the demo.
2. **No Streamlit.** React only.
3. **No fine-tuning, no model training.** Out of scope.
4. **If NeMo Curator won't install, proceed to Tier 0 with equivalent-logic stages and label them as such.** Do not burn more than 45 minutes on install before falling back. Record the fallback in README.
5. **Commit after every tier passes.** Working state must never be lost.
6. **Real data only.** Input must be actual downloaded RBI/bank PDFs, not fabricated text.

---

## 3. ITERATION BUDGET AND STOP CONDITIONS

- **Max 3 attempts per individual check.** After 3 failures on one check, STOP, mark it failed in `STATUS.md`, and move to the next check. Do not loop indefinitely on one problem.
- **Hard stop on Tier 0 at 60% of available time.** If Tier 0 isn't green by then, stop adding scope and spend all remaining time making what exists reliable.
- **Stop entirely when:** all Tier 0 checks pass AND either (a) Tier 1 passes, or (b) time budget is exhausted.
- **Never start Tier 2 with any Tier 0 check red.**

### Escalate to the human (don't guess) when:
- NeMo Curator install fails in a way that suggests a fixable environment issue
- A required PDF source is unreachable / rbi.org.in blocks download
- An API key is needed for Tier 2 and none is configured
- Any check would require faking data to pass

---

## 4. BUILD ORDER

```
1. Scaffold repo + STATUS.md
2. Download real PDFs           → T0.1
3. Extraction                   → T0.2
4. Pipeline skeleton (stages as pluggable steps)
5. Dedup stage                  → T0.4
6. Quality filter stage
7. PII redaction stage          → T0.5   ← SPEND REAL TIME HERE, it's the centrepiece
8. JSONL output                 → T0.6
9. Full pipeline run            → T0.3
10. React dashboard scaffold    → T0.7
11. Wire stage counts into UI   → T0.8
12. Wire PII before/after into UI → T0.9
13. README honesty section      → T0.10
    ─── TIER 0 COMPLETE, COMMIT, BREATHE ───
14. Attempt real NeMo Curator integration → T1.x
15. Only then: narrative drafter → T2.x
```

---

## 5. PIPELINE DESIGN NOTES

- **Stage ordering is fixed:** extract → clean → language ID → dedup → quality filter → **PII redact** → output.
- **PII redaction comes AFTER dedup, never before.** Dedup relies on consistent content; redacting first breaks hash matching. This ordering is itself a talking point in the demo.
- Every stage must emit a record: `{stage, docs_in, docs_out, removed, reason_counts}`. The dashboard reads this.
- Write per-stage output to disk so any stage can be inspected independently and the pipeline is restartable.
- PII to target (Indian context): person names, PAN numbers, Aadhaar-style numbers, account numbers, addresses, phone numbers, email addresses, dates of birth.

---

## 6. DASHBOARD REQUIREMENTS (React)

Minimum viable, in priority order:

1. **Pipeline funnel view** — each stage as a bar/step showing docs in → docs out, with removal counts. This is the money shot.
2. **PII before/after panel** — real extracted text with redactions highlighted. Second most important.
3. **Corpus summary** — total docs, total tokens/chars, duplicates removed, PII entities redacted, final output size.
4. **Document list** — clickable, shows what happened to each document.
5. (Tier 2) **Narrative drafter page.**

Keep styling clean and minimal. Do not spend time on visual polish until Tier 0 logic is green. No component library dependency that risks install failure — plain React + CSS is fine.

---

## 7. STATUS TRACKING

Maintain `STATUS.md` at repo root, updated after every check attempt:

```markdown
# Build Status
Last updated: <timestamp>

## Tier 0
- [x] T0.1 PDFs downloaded — 18 files
- [x] T0.2 Extraction — 18/18 ok
- [ ] T0.3 Pipeline end-to-end — FAILING: <exact error>
...

## Blockers
- <anything needing the human>

## Fallbacks taken
- <e.g. "NeMo Curator install failed after 45min; using equivalent-logic stages, labelled in UI">
```

This file is how the human checks progress without reading code.

---

## 8. DEFINITION OF DONE

All Tier 0 checks green, committed, `README.md` honestly documents real vs simulated, `STATUS.md` current, and the demo can be run from a clean clone with documented commands.

If Tier 0 is green and time remains, proceed to Tier 1. If Tier 1 is green and time remains, proceed to Tier 2. **At no point trade Tier 0 reliability for Tier 2 ambition.**
