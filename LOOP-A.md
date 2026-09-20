# LOOP A — Real NeMo Curator Installation & Integration

**Read `CONTEXT.md` fully first — especially §2 (frozen contracts) and §4.**

**Owner scope:** get the actual NeMo Curator library running, then swap the
equivalent-logic stages for real Curator API calls, one stage at a time, without
breaking the contracts in CONTEXT.md §2.

**Files you own:** environment/setup scripts (new). You will edit the *internals* of
`pipeline/extract.py`, `pipeline/quality.py`, `pipeline/pii.py`, `pipeline/dedup.py` —
but every function must still produce the exact same JSON shapes as today. Streams B and
C are editing these same files' *logic* in parallel — coordinate before touching a
function they're also working on. When in doubt, message the team before editing
`quality.py` or `pii.py` internals; A should generally land its swap for a stage AFTER
B/C have stabilized their custom-rule additions to that stage, not before.

**Git branch:** `stream-a-curator`

---

## THE GOAL (machine-decidable)

> `pip show nemo-curator` succeeds, and at least the quality-filter and PII-redaction
> stages call NeMo Curator's real `ProcessingStage`/`Pipeline` API instead of the
> equivalent-logic reimplementation, while the pipeline still produces output matching
> every contract in CONTEXT.md §2.

## WHY THIS IS THE HIGHEST-LEVERAGE STREAM

Every question TCS asked in the last meeting ("is this equal to Curator?") gets a
strictly better answer once this lands. It also directly unblocks the most credible
demo moment: NVIDIA's actual `nvidia/quality-classifier-deberta` and GLiNER-PII models
running on real Indian KYC text, not our heuristic stand-ins.

---

## TIERED ACCEPTANCE

### TIER 0 — MUST SHIP

| # | Check | How to verify |
|---|---|---|
| A0.1 | Diagnose exactly why install failed on Windows | Exact pip error captured, root cause identified (confirmed: `fasttext`/`cosmos-xenna` wheel builds need C++ toolchain) |
| A0.2 | NeMo Curator installs successfully in SOME environment | `pip show nemo-curator` exits 0, in WSL2, a Linux VM, or the official NeMo Framework container — pick whichever is fastest to stand up |
| A0.3 | A trivial NeMo Curator pipeline runs end to end | Official quickstart example runs without modification, proving the install actually works, not just that pip didn't error |
| A0.4 | Document the working environment setup | A `SETUP.md` any teammate can follow to get the same working install, in case others need to run against real Curator too |

### TIER 1 — REAL INTEGRATION

| # | Check |
|---|---|
| A1.1 | Quality filter stage calls real `nvidia/quality-classifier-deberta` via Curator's `ProcessingStage` API, output still matches the chunk record contract |
| A1.2 | PII stage calls real GLiNER-PII via Curator, output still matches the chunk record contract, `pii_redacted` flag still set correctly |
| A1.3 | Dedup stage uses Curator's real exact+fuzzy dedup implementation |
| A1.4 | Side-by-side comparison run: same 19 PDFs through equivalent-logic pipeline AND real Curator pipeline, results diffed and documented — this is genuinely interesting data (does the real classifier catch different chunks than our heuristic did? Does GLiNER-PII catch more/fewer entities than spaCy+regex?) |

### TIER 2 — IF TIME ALLOWS

| # | Check |
|---|---|
| A2.1 | Language ID stage uses Curator's real implementation too |
| A2.2 | Full pipeline runs exclusively through real Curator `ProcessingStage`/`Pipeline`, equivalent-logic code kept only as a documented fallback |

---

## HARD RULES

1. **Never change a contract shape to make integration easier.** If Curator's native
   output doesn't match a contract field-for-field, write an adapter function that maps
   it to the contract, not the other way around.
2. **Land stages one at a time**, each fully verified against Tier 0-equivalent checks,
   never all four at once — a big-bang swap makes it impossible to tell which stage
   broke something.
3. **Keep the equivalent-logic code available**, don't delete it — if a real-Curator
   stage has issues under time pressure, falling back should be a one-line change, not
   a git-history archaeology exercise.
4. **The A1.4 comparison data is valuable even if nothing else in Tier 1 lands** — if
   you only get one thing done, get the quality-filter comparison, since "here's what
   the real classifier caught that our heuristic missed" is a genuinely interesting
   thing to show TCS.

## STOP CONDITIONS

- If A0.2 doesn't land within the first 3-4 days, escalate to the team — the whole
  Tier 1 depends on it, and B/C/D can keep working regardless, but the team needs to
  know if "real Curator" is at risk for the final deadline.
- Never fake a comparison result. If the real Curator classifier is unavailable and you
  can't get a genuine before/after, say so plainly rather than estimating one.
