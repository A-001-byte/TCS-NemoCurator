# Held-Out Quality Review

**Author:** Kunal (Task K3 from `04_KUNAL.md`)
**Date:** Wednesday 21 Oct 2026
**Branch:** `feat/kunal-tests-tokens`
**Scope:** Review of heuristic quality filtering (`low_alpha_ratio`) across the 16 held-out documents, and evaluation of regulatory keyword tagging (`regulatory_tagged`) on `rbi_kyc_directions_2025_commercial_banks.pdf`. As specified in the work plan, this review is observational; no pipeline code or thresholds were modified.

---

## 1. Corpus Verification & Data Pipeline Context

All **16 held-out PDFs** specified in `00_TEAM_SUMMARY.md` were confirmed present in `data/raw/` (of 35 total raw PDFs):
1. `rbi_kyc_directions_2025_commercial_banks.pdf`
2. `rbi_kyc_directions_2025_nbfc.pdf`
3. `rbi_kyc_directions_2025_urban_coop_banks.pdf`
4. `rbi_fraud_risk_directions_2026_commercial_banks.pdf`
5. `rbi_ppi_master_direction.pdf`
6. `fiu_india_aml_cft_guidelines_vda_2023.pdf`
7. `fiu_india_insurers_aml_guidelines.pdf`
8. `fiu_india_reporting_format_guide_v2_2.pdf`
9. `fiu_india_rbi_ctr_circular_2010.pdf`
10. `fiu_india_annual_report_2021_22.pdf`
11. `amfi_sebi_aml_minimum_standards_2024.pdf`
12. `protium_kyc_aml_policy_2023.pdf`
13. `vivriti_kyc_aml_policy_nov2023.pdf`
14. `rajkot_peoples_coop_bank_kyc_2025_26.pdf`
15. `jsa_prism_rbi_kyc_directions_dec2025.pdf`
16. `jsa_prism_aml_cft_guidelines_jul2023.pdf`

### Pipeline Context for Candidate Reconstruction
In our pipeline architecture, the quality filter stage (`pipeline/quality.py`) writes surviving chunks to `data/filtered/chunks.jsonl` and summary counts to `_stage_record.json`. It does not write rejected chunks to a separate output file.

To review `low_alpha_ratio` rejections, candidate chunks were evaluated by reading all 1,337 deduplicated chunks (`data/deduped/chunks.jsonl`) belonging to the 16 held-out documents directly through the imported `pipeline.quality.quality_reason` function under the active configuration (`MIN_WORDS = 15`, `MIN_ALPHA_RATIO = 0.5`, `MAX_SYMBOL_RATIO = 0.3`, `MIN_LEXICAL_DIVERSITY = 0.20`).

Across the 16 held-out documents, this verification confirmed:
- Total input chunks evaluated: 1,337
- Total rejected chunks: 36
  - `low_alpha_ratio`: 29 chunks
  - `high_symbol_ratio`: 7 chunks
  - `too_few_words`: 0 chunks
  - `low_lexical_diversity`: 0 chunks

---

## 2. Review 1: Low Alpha Ratio (`low_alpha_ratio`)

### Candidate Pool & Complete Review Methodology
Selecting the first 20 chunks sorted by `chunk_id` would bias the sample towards files whose names appear earlier alphabetically (e.g. `amfi_...` and `fiu_...`). Because the total candidate pool across all 16 held-out PDFs consists of only **29 chunks**, sampling was eliminated and **all 29 candidate chunks were reviewed individually**.

The complete list of evaluated candidate chunk IDs (denominator = 29):
1. `amfi_sebi_aml_minimum_standards_2024__0`
2. `fiu_india_aml_cft_guidelines_vda_2023__0`
3. `fiu_india_aml_cft_guidelines_vda_2023__1`
4. `fiu_india_annual_report_2021_22__20`
5. `fiu_india_annual_report_2021_22__26`
6. `fiu_india_annual_report_2021_22__3`
7. `fiu_india_insurers_aml_guidelines__30`
8. `fiu_india_insurers_aml_guidelines__33`
9. `fiu_india_insurers_aml_guidelines__37`
10. `fiu_india_insurers_aml_guidelines__39`
11. `fiu_india_insurers_aml_guidelines__44`
12. `fiu_india_insurers_aml_guidelines__69`
13. `fiu_india_reporting_format_guide_v2_2__1`
14. `fiu_india_reporting_format_guide_v2_2__10`
15. `fiu_india_reporting_format_guide_v2_2__2`
16. `fiu_india_reporting_format_guide_v2_2__3`
17. `fiu_india_reporting_format_guide_v2_2__4`
18. `fiu_india_reporting_format_guide_v2_2__5`
19. `fiu_india_reporting_format_guide_v2_2__6`
20. `fiu_india_reporting_format_guide_v2_2__7`
21. `fiu_india_reporting_format_guide_v2_2__8`
22. `fiu_india_reporting_format_guide_v2_2__9`
23. `rbi_fraud_risk_directions_2026_commercial_banks__0`
24. `rbi_fraud_risk_directions_2026_commercial_banks__1`
25. `rbi_kyc_directions_2025_commercial_banks__0`
26. `rbi_kyc_directions_2025_commercial_banks__1`
27. `rbi_kyc_directions_2025_nbfc__0`
28. `rbi_kyc_directions_2025_urban_coop_banks__0`
29. `rbi_kyc_directions_2025_urban_coop_banks__1`

### Analysis & Categorization of All 29 Candidates
All 29 rejected candidates were examined to assess whether they constituted non-training artifacts or lost grammatical text:
- **Tables of Contents & Section Outlines (18 chunks):** Dot leaders (`.......`), section titles, and page numbers (`amfi_...__0`, `fiu_...vda...__0`, `__1`, `fiu_...annual...__3`, `fiu_...insurers...__44`, `fiu_...format...__1`–`__10`, `rbi_...fraud...__1`, `rbi_...commercial...__1`, `rbi_...urban...__1`).
- **Cover Page Headers & Circular Identifiers (4 chunks):** Bilingual letterhead metadata with reference numbers and TOC starts (`rbi_...fraud...__0`, `rbi_...commercial...__0`, `rbi_...nbfc...__0`, `rbi_...urban...__0`). In these chunks, non-ASCII Devanagari script is not matched by `[A-Za-z]`, and combined with numeric dates and reference paths, alpha ratio falls below 0.5. None contains narrative training text.
- **Blank Form & Questionnaire Templates (4 chunks):** Form layouts dominated by checkbox sequences (`□□□□□□`) and signature lines (`fiu_india_insurers_aml_guidelines__30`, `__33`, `__37`, `__39`).
- **Raw Numerical / Statistical Series (2 chunks):** Unformatted chart data strings without sentence structure (`fiu_india_annual_report_2021_22__20`, `__26`).
- **Technical Schema Specification (1 chunk):** Fixed-width data transmission table with byte positions (`fiu_india_insurers_aml_guidelines__69`).

### Short Example Excerpts (PII-Safe)
1. **Table of Contents (`fiu_india_reporting_format_guide_v2_2__1`, alpha: 0.247):**
   > `FIU-IND .................................................................................................................1 1.2 Earlier reporting formats ..................................................`
2. **Form Layout (`fiu_india_insurers_aml_guidelines__37`, alpha: 0.335):**
   > `Tel (with STD code) □□□□□□□□□□□□□□□ 2.14 Fax □□□□□□□□□□□□□□□ 2.15 E-mail PART 3 DETAILS OF REPORTING BRANCH/LOCATION □□□□□□□□□□...`
3. **Chart Coordinates (`fiu_india_annual_report_2021_22__20`, alpha: 0.450):**
   > `several years is presented below: 1600000 1436340 1400000 1200000 1000000 800000 602057 547013 600000 473006 433761... Chart 1: Year wise...`

### Candidate Review Finding
- **False Drops (Lost Valid Text):** 0 / 29 in the reviewed candidates.
- **Finding:** In this specific held-out candidate set, `MIN_ALPHA_RATIO = 0.5` did not discard narrative text. Because all 29 candidate chunks across the 16 held-out PDFs were reviewed, this finding reflects the full held-out low-alpha pool, though it does not imply zero false drops across untested corpora.

---

## 3. Review 2: Regulatory Keyword Tagging

Evaluated on the surviving chunks of `rbi_kyc_directions_2025_commercial_banks.pdf` (154 surviving chunks).
Under the active pipeline rule, a chunk is marked `regulatory_tagged: True` if it contains $\ge 2$ distinct keywords from `REGULATORY_KEYWORDS` (`MIN_KEYWORD_MATCHES_FOR_TAG = 2`).

- **Total Surviving Chunks in Document:** 154
- **Tagged Chunks Pool:** 90 (58.4% of surviving chunks)
- **Untagged Chunks Pool:** 64 (41.6% of surviving chunks)

### Sampling Methodology (Fixed Random Seed)
To avoid ordering bias from sequential chunk IDs, 20 chunks from each pool were selected using Python's `random.sample()` with a recorded fixed seed:
```python
random.seed(42)
sampled_tagged = sorted(random.sample(tagged_chunk_ids, 20))

random.seed(42)
sampled_untagged = sorted(random.sample(untagged_chunk_ids, 20))
```

---

### Part A: Tagged Sample Review (20 of 90)

**Sampled Chunk IDs (N=20, denominator=90):**
`__102`, `__103`, `__117`, `__119`, `__12`, `__127`, `__162`, `__17`, `__18`, `__19`, `__21`, `__27`, `__5`, `__68`, `__72`, `__74`, `__8`, `__81`, `__89`, `__95` (prefixed by `rbi_kyc_directions_2025_commercial_banks`).

#### Sample Observations
All 20 sampled chunks contain substantive regulatory rules and operational obligations:
- `__102` & `__103`: FATCA / CRS due diligence and compliance audits (`designated director`, `due diligence`).
- `__117`: Walk-in customer cash transaction verification above ₹50,000 (`aml`, `ctr`, `str`).
- `__119`: Staff training policy on KYC / AML / CFT (`aml`, `cft`, `know your customer`, `kyc`).
- `__12`: Submission timeline for Officially Valid Documents (`aadhaar`, `foreign national`).
- `__127`: Designated person asset-freezing intimation to FIU-IND (`fiu-ind`, `sebi`, `str`, `suspicious transaction report`).
- `__162`: Beneficial ownership disclosure under UAPA (`beneficial owner`, `beneficial ownership`, `designated individual`).
- `__17`, `__18`, `__19`: Statutory definitions of CDD, periodic updation, and customer identification (`cdd`, `cip`, `ckycr`, `shell bank`).
- `__68`, `__72`, `__74`: Periodic KYC updation operational requirements (`kyc`, `periodic updation`).

#### Short Example Excerpts (PII-Safe)
1. **Periodic Updation (`__72`, density: 0.0889):**
   > `authority at the time of periodic updation of KYC. (iii) The bank provides an acknowledgment to the customer mentioning the date of receipt...`
2. **Correspondent Banking / Shell Bank (`__19`, density: 0.0556):**
   > `licensed, and which is unaffiliated with a regulated financial group that is subject to effective consolidated supervision. (xxii) ‘Customer Identification’ means...`

#### Tagged Sample Finding
- **False Tags (Irrelevant Chunks Tagged):** 0 / 20 in the reviewed sample.
- **Scope Limit:** While this sample demonstrates high precision on this specific document, this finding is bounded by the sample size (20/90) and cannot be generalized as a claim of 100% precision across the entire corpus.

---

### Part B: Untagged Sample Review (20 of 64)

**Sampled Chunk IDs (N=20, denominator=64):**
`__109`, `__11`, `__113`, `__115`, `__120`, `__142`, `__143`, `__144`, `__147`, `__164`, `__171`, `__22`, `__43`, `__56`, `__60`, `__79`, `__84`, `__91`, `__93`, `__96` (prefixed by `rbi_kyc_directions_2025_commercial_banks`).

#### Sample Breakdown by Keywords Matched
- **1 Keyword Match (9 chunks):** `__113` (`fiu-ind`), `__120` (`rbi`), `__142` (`sebi`), `__143` (`sebi`), `__144` (`sebi`), `__147` (`fiu-ind`), `__60` (`beneficial owner`), `__84` (`sebi`), `__93` (`sanctions`).
- **0 Keyword Matches (11 chunks):** `__109`, `__11`, `__115`, `__164`, `__171`, `__22`, `__43`, `__56`, `__79`, `__91`, `__96`.
- **Sum:** 9 + 11 = 20 chunks.

#### Sample Assessment
- **Appropriately Untagged / Administrative Boilerplate (3 chunks):**
  - `__120`: Statutory repeal and savings clause (transitional legal machinery).
  - `__147`: Government department and police commissioner routing directory (contact table).
  - `__171`: Government order reference and administrative notice.
- **Substantive Regulatory Provisions Left Untagged (17 chunks):**
  - `__11`: Deemed Officially Valid Documents (utility bills, property tax receipts) under UIDAI guidance.
  - `__113`: Beneficiary bank cross-border wire transfer monitoring and suspicious transaction reporting to FIU-IND under PML Rules.
  - `__115`: Mandatory name screening prohibiting cross-border wire transfers with designated persons/entities, wire record retention under paragraph 50, and demand draft remittance rules.
  - `__142`, `__143`, `__144`: Asset unfreezing verification and reporting to Central UAPA Nodal Officer.
  - `__164`: Prevention of Money-Laundering Act asset freezing mandates.
  - `__22`: Wire transfer ordering person definition and serial payment requirements.
  - `__43`: Digital V-CIP OTP customer verification declaration.
  - `__56`: Jail inmate account opening and monitoring safeguards.
  - `__60`: Company account opening attorney and management verification.
  - `__79`: Politically Exposed Persons (PEPs) definition and family member scrutiny.
  - `__84`: Eligible Foreign Investor / Custodian account opening standards.
  - `__91`: Section 51A of UAPA obligations and Nodal Officer procedures.
  - `__93`: Section 12A of WMD Act 2005 transaction prohibition directives.
  - `__96`: Customer information confidentiality and secrecy provisions.
  - `__109`: Originator and beneficiary information retention in wire transfers.

#### Short Example Excerpts (PII-Safe)
1. **OVD Address Verification (`__11`, 0 keywords matched):**
   > `Authority of India (UIDAI) issues. (b) when the customer furnishes an OVD that does not have an updated address, the bank shall deem the following documents... to be OVDs for the limited purpose of proof of address:- • utility bill...`
2. **PEPs Definition (`__79`, 0 keywords matched):**
   > `to continue the business relationship; (2) These instructions shall also apply to family members or close associates of PEPs. Explanation: For the purpose of this paragraph, ‘Politically Exposed Persons’ (PEPs) are individuals who are or have been entrusted with prominent public functions...`
3. **Wire Sanctions & Records (`__115`, 0 keywords matched):**
   > `undertaking cross-border wire transfer with respect to name screening (such that they do not process cross-border transactions of designated persons and entities): The bank is prohibited from conducting transactions with designated persons and entities...`

#### Untagged Sample Finding
- **Missed Tags (Substantive Chunks Left Untagged):** 17 / 20 in the reviewed sample.
- **Scope Limit:** This 17/20 finding is specific to this sample from `rbi_kyc_directions_2025_commercial_banks.pdf` (a pure regulatory circular where almost all text is normative). It must not be cited as the overall false-negative rate of the pipeline or generalized to heterogeneous mixed documents.

---

## 4. Evaluation of Keyword & Threshold Options (For Ankit)

Because `regulatory_tagged` requires $\ge 2$ distinct keywords, **adding a single vocabulary term cannot tag a chunk that currently matches zero keywords**.

Each candidate adjustment below was checked against the tagger's actual matching rules (`_keyword_spans` with regex boundaries and longest-match resolution):

### Checked Impact of Candidate Keyword Additions

| Proposed Term | Target Missing Chunks | Current Matches | Matches With Term (Verified via Tagger) | Tags Chunk? ($\ge 2$) | Potential False-Positive Risks / Trade-offs |
|---|---|---|---|---|---|
| `"uapa"` | `__142`, `__143`, `__144` | 1 (`sebi`) | 2 (`sebi`, `uapa`) | **Yes** | Very low risk in banking text (refers specifically to anti-terror sanctions orders under Sec 51A). |
| `"uapa"` | `__91` | 0 | 1 (`uapa`) | **No** (needs 2nd term) | If combined with `"wmd act"` (which also appears in `__91`), chunk reaches 2 matches and tags. |
| `"pml rules"` | `__113` | 1 (`fiu-ind`) | 2 (`fiu-ind`, `pml rules`) | **Yes** | Low risk. The dictionary has `"pmla"` but not `"pml rules"`, which appears frequently in circulars. |
| `"peps"`, `"politically exposed persons"` | `__79` | 0 | 2 (both plurals match) | **Yes** | Low risk. `__79` was missed because the keyword list contains only singulars (`pep`, `politically exposed person`). |
| `"ovd"` alone | `__11` | 0 | 1 (`ovd`) | **No** (needs 2nd term) | Adding only `"ovd"` leaves `__11` at 1 match (untagged). |
| `"ovd"`, `"uidai"` together | `__11` | 0 | 2 (`ovd`, `uidai`) | **Yes** | `"ovd"` is a 3-letter acronym requiring word-boundary regex to prevent sub-string collision. `"uidai"` is highly specific. |
| `"wmd"`, `"wmd act"` | `__93` | 1 (`sanctions`) | 2 (`sanctions`, `wmd act`) | **Yes** | `"wmd act"` is very specific; bare `"wmd"` could theoretically match unrelated acronyms. |
| `"wire transfer"` | `__109`, `__22`, `__115` | 0 | 1 (`wire transfer`) | **No** (remains at 1) | Common banking operational term; adding it alone leaves all three chunks at 1 match (untagged). |

*(Note: Effects for terms evaluated above were verified against the tagger’s tokenization and span-resolution logic; any other broader corpus projections should be treated as estimates subject to empirical validation across the 35 PDFs).*

### Summary of Architectural Options for Stage Owner

1. **Option A: Keep `MIN_KEYWORD_MATCHES_FOR_TAG = 2` and add targeted plural/variant terms**
   - *Pros:* Preserves precision across heterogeneous corpora while recovering high-value regulatory chunks that contain multiple missing terms (e.g., `__79` via plural PEPs, `__11` via OVD + UIDAI, `__91` via UAPA + WMD).
   - *Trade-off:* Does not tag chunks that discuss a single regulatory concept in isolation.
2. **Option B: Reduce threshold to `MIN_KEYWORD_MATCHES_FOR_TAG = 1`**
   - *Pros:* Immediately tags single-concept regulatory chunks (e.g., `__113`, `__60`, `__84`).
   - *Risk / Trade-off:* Significantly increases false positives. As documented in `pipeline/quality.py`, $N=1$ tagged 84.8% of chunks in the initial corpus because a single mention of `"FIU"` or `"RBI"` in a standard corporate disclaimer or form header was sufficient to tag the chunk.
3. **Option C: Document-level routing / metadata flag**
   - *Pros:* For official gazettes and Master Directions, document-level metadata can indicate regulatory origin, while chunk-level keyword density (`regulatory_density_score`) is used for ranking and filtering rather than binary inclusion.
