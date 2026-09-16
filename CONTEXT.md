# PROJECT CONTEXT — Read This First

You are picking up a project cold. This document is the entire situation. Read all of it before writing code.

---

## 1. THE SITUATION

### Who
- **Buster** (Ankit Vyavahare) — CSE student, Vishwakarma Institute of Technology, Pune. Specializing in Cybersecurity + Blockchain.
- A **faculty guide** arranged contact with **TCS**.
- A **TCS engineer** (the stakeholder) works on BFSI + NVIDIA tooling. He is **short-handed / working largely alone**. He has data. He wants something that *eases his actual work*.

### The timeline (CRITICAL)
- An initial TCS consultation meeting already happened.
- The TCS engineer said: build something, show me on **the 18th**, and if it's useful, I'll give you work.
- **The showcase is TOMORROW.** There is ONE EVENING of build time.
- Treat this as the real evaluation, not a casual follow-up.

### What this means for scope
Ruthless minimalism. A small thing that **actually runs** beats a large thing that half-runs. Every hour spent on ambition is an hour not spent on "does the demo work on the first try."

---

## 2. WHAT THE STAKEHOLDER ACTUALLY ASKED FOR

Direct quotes / paraphrases from the meeting, in his words:

- *"We are not fine-tuning yet. Main process is creating the data."*
- *"40-50 PDF files, make data ready for fine-tuning."*
- *"Bank regulatory data, KYC regulatory data — create meaningful data for fine-tuning."*
- *"Crawl BFSI data and make meaningful data."*
- *"Go into fraud detection, fraud penalty."*
- *"NeMo Curator — Megatron tokenising."*
- *"If you can pick up KYC of India."*
- He mentioned **we are the first to try Curator** (inside his scope).
- He pointed at the **NVIDIA-NeMo GitHub org** and specifically the **Megatron-Bridge** repo diagram.

### Translation
He wants a **working NeMo Curator data-preparation pipeline on Indian banking/KYC regulatory documents**, producing clean fine-tuning-ready output. He explicitly does NOT want fine-tuning or model training — that is the next stage (Megatron-Bridge) and is out of scope.

---

## 3. PROJECT HISTORY — HOW WE GOT HERE

This matters because you should not resurrect abandoned directions.

### Abandoned idea #1: "Curation Integrity Audit" (bias audit)
Original pitch was to audit whether NeMo Curator's quality classifier is biased (prefers AI-written text, penalizes Indian English, lets fluent poison through). Backed by real research:
- ACM TOIS: transformer quality scorers rate GPT-generated text **10–20% higher** than human text
- Gururangan et al. (EMNLP 2022), "Whose Language Counts as High Quality?" — quality filters encode class/geography ideology
- Bhatt et al. (AACL 2022), "Re-contextualizing Fairness in NLP: The Case of India"
- Pretraining poisoning research: fluent adversarial text survives quality filtering

**Status: DEMOTED, not deleted.** It was the right pitch for a consultation where we needed a clever angle. It is NOT what he asked to be built. It may appear as ONE supporting slide/section. Do not build the project around it.

### Abandoned idea #2: "Data Bill of Materials / audit provenance layer"
Dropped because **CuratorKIT** (arXiv 2026) already covers document-level curation auditing. Do not rebuild it.

### CURRENT DIRECTION
**An STR/SAR narrative-drafting assistant, and the NeMo Curator pipeline that produces its training data.**

Rationale from BFSI research (see §5): the single biggest time sink for Indian BFSI compliance analysts is **writing Suspicious Transaction Report narratives** — hours per report, and the time goes into *writing and formatting*, not the actual judgment call. To fine-tune a model that drafts these, you first need a clean, PII-safe corpus of Indian regulatory text. That corpus does not exist ready-made. **Building it is exactly the NeMo Curator job he asked for.**

So:
- **The deliverable he asked for** = the curation pipeline (regulatory PDFs → clean, deduped, PII-redacted, fine-tuning-ready corpus)
- **The "so what" that makes it land** = a thin narrative-drafter showing what the curated corpus is FOR

---

## 4. TECHNICAL FACTS YOU MUST NOT GET WRONG

### NeMo Curator
- NVIDIA's GPU-accelerated data curation library. Part of the NeMo Framework.
- Capabilities: exact / fuzzy / semantic deduplication, heuristic + classifier-based quality filtering, PII detection and redaction, language ID, domain & safety classification, downstream-task decontamination, synthetic data generation.
- Built on RAPIDS (cuDF, cuML, cuGraph) + Ray.
- **VERSION WARNING:** 1.x is a MAJOR REWRITE. The old `DocumentDataset` and `nemo_curator.modules.*` API from 0.x is GONE. You now compose `ProcessingStage` objects into a `Pipeline` and run it with an executor. **Most tutorials online are 0.x and will not work.** Always check the current docs/repo, never copy 0.x imports.
- CPU install path exists: `pip install "nemo-curator[text_cpu]"`
- The quality classifier shipped is `nvidia/quality-classifier-deberta` (a DeBERTa model).
- PII redaction can use NVIDIA's **GLiNER-PII** model (there's a `gliner_pii_redaction.ipynb` tutorial in the repo under `tutorials/text/`).
- Repo: `github.com/NVIDIA-NeMo/Curator`

### Pipeline ordering rule (matters, and signals competence)
**Redact PII AFTER deduplication, never before.** Exact and fuzzy dedup depend on consistent document content; redacting first breaks hash-based matching because PII strings get replaced inconsistently.

### Where we stop
NVIDIA's own lifecycle diagram:
```
Data Curation → Pre-training & SFT/LoRA → Post-training/RL → Inference
  [Curator]      [Megatron-Bridge,          [RL]            [Export-Deploy,
                  AutoModel]                                  Eval, Guardrails]
```
**We build the leftmost box only.** Megatron-Bridge is the training library (takes curated data, trains models, bidirectional HuggingFace checkpoint conversion, built on Megatron Core). We deliberately do not touch it. Say so explicitly in any output — it shows we understand the architecture.

### Other NVIDIA thing that came up
**NeMo Agent Toolkit (NAT)**, package `nvidia-nat`, formerly AgentIQ — framework-agnostic tooling for taking AI *agents* to production (observability, eval, deployment, auth, rate limiting). **This is a DIFFERENT product from Curator.** Do not conflate them. Curator = data prep before training. NAT = hardening agents after they're built.

---

## 5. DOMAIN RESEARCH — INDIAN BFSI COMPLIANCE

This is why the current direction was chosen. Do not re-derive it.

### The five heaviest time sinks for KYC/AML analysts
1. Document extraction and data entry
2. Evidence compilation before case review
3. PEP / sanctions screening alert triage
4. Investigation synthesis
5. **STR/SAR narrative drafting** ← the biggest, and our target

### Why narrative drafting specifically
- Investigators spend **several hours per narrative**.
- The slow part is **writing and formatting to regulator-prescribed structure**, not deciding whether something is suspicious.
- Narratives must cover: who, what, when, where, why suspicious, in a logical chronological format.
- Quality varies by analyst experience and style → inconsistency is a known problem.
- It is structured text generation from structured facts — an ideal LLM task.

### India-specific regulatory landscape (use these, not US equivalents)
- **RBI** is the primary regulator. Also IRDAI (insurance), SEBI (securities).
- **RBI Master Direction — Know Your Customer (KYC) Direction, 2016**, updated periodically. This is the core document.
- **FIU-IND** is where STRs are filed in India (NOT FinCEN — that's US. Do not use FinCEN framing).
- **CKYCR** = Central KYC Records Registry. "KYC Templates" exist for reporting to it.
- Re-KYC cadence: low-risk every 10 years, medium every 8, high-risk every 2.
- RBI inspection is **evidence-driven** — inspectors demand timestamped records, documented rationale, audit trails showing who reviewed what and when. Assertions of compliance are not accepted.
- Relevant terms: CDD (Customer Due Diligence), EDD (Enhanced Due Diligence), UBO (Ultimate Beneficial Owner), PEP (Politically Exposed Person), MLRO (Money Laundering Reporting Officer), Form 60 (for those without PAN), STR vs SAR (STR = the term used in India).

### Data sources (ALL PUBLIC — no TCS data needed)
- RBI Master Directions and circulars — `rbi.org.in`
- Indian bank KYC/AML policy PDFs — every bank publishes one (Bank of India, Central Bank of India, etc.)
- Public sanitized STR/SAR narrative examples and templates from AML training sites
- Public AML case scenarios for demo input facts

**We deliberately do NOT need his client data.** Volunteering that is a positive signal in a BFSI/compliance room. If he offers a sanitized sample, fold it in; never block on it.

---

## 6. HARD CONSTRAINTS

### Do
- Use **React** for any dashboard/UI. **NOT Streamlit.** (Explicit user instruction.)
- Use real, public RBI/KYC PDFs as input — not synthetic placeholder text.
- Keep the two halves **independently demoable** (see §7).
- Be honest in all output about what is real vs simulated.

### Do NOT
- Do NOT fine-tune or train any model. Explicitly out of scope and there's no time.
- Do NOT use Streamlit.
- Do NOT claim NeMo Curator is doing something it isn't. If the library doesn't install in time and you implement the stage logic manually, **label it clearly** as "NeMo-Curator-equivalent stage, library integration pending." Faking library integration in front of NVIDIA-adjacent TCS engineers is the single worst possible outcome.
- Do NOT rebuild the bias-audit or DBOM ideas as the main project.
- Do NOT invent statistics. The three research findings in §3 are real and citable; anything else needs a source.
- Do NOT use FinCEN/US framing for an Indian regulatory demo.

### Team reality
Buster's team is **unreliable**. Assume he builds alone. No critical-path task may depend on a teammate delivering.

---

## 7. ARCHITECTURE — THE TWO HALVES

This split is the single most important de-risking decision. Preserve it.

### Half 1 — The Curation Pipeline (THE DELIVERABLE)
Real RBI/KYC PDFs in → clean, deduped, PII-redacted, fine-tuning-ready JSONL out.

Stages, in order:
1. PDF text extraction
2. Cleaning / normalization
3. Language ID
4. Deduplication (exact, then fuzzy) — **regulatory boilerplate repeats constantly, so this visibly fires**
5. Quality filtering
6. **PII redaction** ← THE CENTREPIECE. KYC docs are full of real-format PII (names, PAN, account numbers, addresses). Visibly catching and removing these on Indian banking documents is the most memorable thing in the whole demo. Worth more than anything else.
7. Output as fine-tuning-ready JSONL

**Half 1 must work standalone.** If Half 2 collapses entirely, Half 1 alone is still a complete, honest answer to what he asked for.

### Half 2 — The Narrative Drafter (THE "SO WHAT")
A thin React front-end. Analyst pastes structured case facts (entity, transaction timeline, red flags) → gets a draft STR narrative in RBI/FIU-IND format, grounded in the curated regulatory corpus from Half 1.

**No fine-tuning.** Use an off-the-shelf LLM prompted with retrieved context from the curated corpus. Say this out loud in the demo: *"we didn't fine-tune — we're showing what the curated corpus would train; here it's driving an off-the-shelf model via retrieval to prove the concept."*

If Half 2 fails, cut it and lean on Half 1.

---

## 8. THE PITCH (for reference — what the demo must support)

> "BFSI compliance analysts spend hours per suspicious-transaction report — not deciding what's suspicious, but writing it up in RBI/FIU format. To fine-tune a model that drafts those, you first need a clean, PII-safe corpus of Indian regulatory text. That corpus doesn't exist ready-made — building it is what NeMo Curator is for. Here's the pipeline: real RBI and KYC documents in; cleaned, deduplicated, PII stripped, fine-tuning-ready out. And here's what it's for — paste the case facts, get a draft narrative grounded in that curated regulatory context. We deliberately stopped before fine-tuning — that's the Megatron-Bridge stage, the next box in NVIDIA's own pipeline."

---

## 9. QUESTIONS TO ASK THE STAKEHOLDER (he invited doubts)

1. Does NeMo Curator 26.02 expose per-stage retention statistics, or do we instrument that ourselves?
2. What document types does your team actually handle most — KYC forms, transaction logs, complaints, internal STR drafts?
3. Can we get a sanitized or synthetic sample of representative documents? (Optional — we're building on public RBI data either way.)
4. What threshold of evidence counts as "proven" to you?
5. Are you using Curator and NAT together in any pipeline, or separately?

---

## 10. STYLE / COMMUNICATION

- Buster prefers **direct, casual, blunt** communication. Honest assessments over encouragement. No padding.
- Flag uncertainty explicitly rather than guessing.
- If something can't be done in the time available, say so immediately rather than half-building it.
