# Demo script (10 minutes)

For the in-person review with TCS. Demo machine: Kunal's Linux laptop (WSL2 Ubuntu, RTX 4050). The numbers below are from `docs/FINAL_NUMBERS.md`, which is generated from the snapshots; if the corpus or a rule changes, regenerate it and update this page.

## 1. Fifteen minutes before

Run these from the repository root, in this order. Nothing needs the internet.

```bash
git fetch --tags && git checkout demo-ready          # the tagged, rehearsed version
source venv-curator/bin/activate                     # the environment from SETUP.md
nvidia-smi | head -5                                 # the GPU is visible (skip if presenting on CPU)
python -m pytest -q                                  # 29+ passed, about a minute
```

Then start the two servers, each in its own terminal:

```bash
python -m pipeline.server                            # terminal 1: API on 127.0.0.1:8000
cd dashboard && npm run dev                          # terminal 2: dashboard on http://localhost:5173
```

Check: `curl -s http://127.0.0.1:8000/api/health` prints `{"ok": true}`, and the dashboard opens with a **Device** pill in the top bar.

Make a small folder of three PDFs for the live upload and the terminal step (about 25 seconds in total):

```bash
mkdir -p demo_pdfs && cp data/raw/bank_of_baroda_kyc.pdf data/raw/fiu_india_brochure.pdf data/raw/rbi_kyc_fidcindia_aug2025.pdf demo_pdfs/
```

## 2. Run of show

| Time | Show | Say |
|---|---|---|
| 0:00 | **Overview** | 35 public PDFs from RBI, FIU-IND, SEBI/AMFI and bank and NBFC websites became **3,325 clean chunks** (about 803,000 tokens) ready for fine-tuning. One PDF is a scan with no text, so 34 were readable. Nothing here is synthetic, and no model was trained. |
| 1:30 | **Pipeline**: click through the seven stages | Heal removes page furniture (3,176 lines). Dedup removes 330 copies and keeps the newest policy version. Quality drops 71 chunks. PII redaction runs after dedup on purpose. Every stage shows what it removed and why. |
| 3:00 | **Process documents**: upload the three PDFs from `demo_pdfs/` | This is the real pipeline on the uploaded files, in a temporary folder. Wait for it (about 25 s), then download the JSON. Point at one `[REDACTED_…]` placeholder in it. |
| 4:30 | **PII redaction** | **68 items**: 47 emails, 13 PIN codes, 3 phones, 2 company IDs, 2 names, 1 SWIFT code. Almost all are official contact details printed in public documents; we redact them anyway. Each rule checks context, for example a PIN code needs an address context and an Aadhaar number must pass its checksum. The examples show the original partly masked next to the redacted text. |
| 5:30 | **NeMo comparison** | We also ran the real NVIDIA NeMo Curator 1.3.0 on the same chunks. Its default filters remove 716 of 3,396 (21%); ours remove 71 (2%). Most of the difference is its repeated-phrase filter hitting report-format tables. These are web-text defaults, so it shows a design difference, not that one side is wrong. We have not hand-checked the chunks only NeMo removes. |
| 6:30 | **Document types** | A small nearest-centroid classifier: **55.9%** right when a document's whole family of near-copies is held out, against 29.4% for always guessing the biggest type. Read the caption: it is not a trained fraud or anomaly model. Four variants were tried on the same 34 documents, so treat the figure as optimistic. |
| 7:30 | **Terminal** | `python -m pipeline.cli run demo_pdfs -o /tmp/out` (about 25 s). It prints the stage table and the device, and writes `curated.jsonl`. Same code path as the dashboard, checked by a test. |
| 8:30 | **Proof** | `python -m pytest -q` is green (show the last run if time is short). The same input gives a byte-identical output on every run. |
| 9:00 | **Honest limits** | Scanned PDFs need OCR (not built). The GPU speeds up only the optional GLiNER and DeBERTa models, 16x and 9x on the RTX 4050, with identical outputs; the default pipeline runs on the CPU, and real NeMo GPU dedup was not run. The tag threshold of 2 keywords misses some real regulatory text. |
| 9:45 | Questions | See `LIKELY_QUESTIONS.md`. |

## 3. Do not

- **Do not click "Re-run pipeline and refresh numbers" on stage.** It re-runs all 35 PDFs and takes 6 to 12 minutes. Show the button, say what it does, and move on.
- Do not say the GPU makes the whole pipeline faster, that the classifier is a fraud model, or that all 35 PDFs were processed.
- Do not quote a number that is not in `docs/FINAL_NUMBERS.md`.

## 4. If something goes wrong

| Problem | Do this |
|---|---|
| The API is down | The dashboard still shows the stored snapshot. Say so, skip the live upload and use the terminal step. |
| The upload is slow | Narrate the stages while it runs; if it passes a minute, show `docs/team/backup/` screenshots and the terminal step. |
| The terminal command fails | Show `docs/FINAL_NUMBERS.md` and the dashboard. |
| The page is blank | Reload; check the dev-server terminal; run `npm run build && npx vite preview` as a fallback. |
| The numbers show 66 PII, not 68 | Name detection is off on that machine (the spaCy model did not load). Say so honestly; the Overview callout states it. |
