# Likely questions, with honest answers

Numbers are from `docs/FINAL_NUMBERS.md`. If a question is not covered, say what we know and what we have not tested.

## What does it do, and who is it for?
It turns banking and KYC regulatory PDFs into clean, de-duplicated, personal-data-redacted text with metadata, ready for fine-tuning a language model, and it shows what every stage removed and why. A bank, a regulator's vendor or an AI team preparing training data would use it.

## Is the data real?
Yes. 35 public PDFs from RBI, FIU-IND, SEBI/AMFI, and bank and NBFC websites, plus two law-firm summaries. Nothing is synthetic. 16 of them were added late and never used when the rules were tuned; running them found 7 false PII alarms, which we fixed (the count went from 75 to 68).

## Were all 35 PDFs processed?
No. 34 were readable. `bank_of_baroda_aml_questionnaire.pdf` is a scan with no text layer, and we do not do OCR. The pipeline reports it and carries on.

## Why not a hosted API?
KYC documents are confidential, so they should not have to leave the customer's machine. A local library and command line cost nothing to host, work offline and give identical results; the local API exists for the dashboard. The three entry points share one code path, and a test checks they return identical output.

## What does the GPU do?
Only the optional models: GLiNER for personal data and the DeBERTa quality signal run 16x and 9x faster on the RTX 4050 (21.4 s to 1.3 s and 4.9 s to 0.5 s on 20 samples), with identical outputs. The default pipeline is regex, spaCy and heuristics on the CPU. NeMo's own GPU dedup needs cuDF; cuDF installs and runs on the RTX 4050, but we did not run NeMo dedup itself.

## What are the 68 PII items?
47 emails, 13 PIN codes, 3 phone numbers, 2 company registration numbers, 2 person names and 1 SWIFT code. Almost all are official contact details printed in public documents. We redact them anyway, and we do not claim to have found private data.

## How do you avoid hiding ordinary numbers?
Every rule checks the surrounding text. A date is only hidden after a birth-date cue, a PIN code needs an address context and a plausible prefix, an Aadhaar number must pass its Verhoeff checksum, a SWIFT code needs a label, and a long number inside a table of figures is left alone. Each rule has a test that fails if the rule is broken.

## Why does NeMo Curator remove 21% and you only 2%?
We ran NeMo Curator 1.3.0's default heuristic filters on the same 3,396 chunks: it removes 716, we remove 71, and 67 are removed by both. Most of NeMo's removals come from its duplicated-phrase filter hitting two FIU report-format guides, which are tables of repeated field descriptions. Its defaults are tuned for web text. We have not hand-checked the 649 chunks only NeMo removes, so we do not say which side is right.

## Why did you reject NVIDIA's quality classifier?
We tested it: it was about 17 times stricter and judged document layout, not quality (it rated 97% of the FIU reporting formats low). It stays available as an optional label that never removes a chunk.

## How good is the document-type classifier?
55.9% when each document's whole family of near-copies is held out, against 29.4% for always guessing the biggest type. It is a small nearest-centroid model on word statistics, not a trained fraud or anomaly model. We tried four variants on the same 34 documents and merged two types after seeing the results, so the number is optimistic. One type, FIU report formats, is never found.

## Why does a chunk count as "regulatory"?
It needs at least 2 different regulatory keywords from a list we pruned. Our own review found that 17 of 20 untagged chunks in the new RBI KYC Directions are real regulatory text, so the threshold is too strict for pure regulations. It is a known trade-off, and changing it would change every number.

## Is the output reproducible?
Yes. The same input gives a byte-identical `curated.jsonl` (same hash) on repeated runs and across the library, the command line and the API. A full run of 35 PDFs takes about 5.5 minutes on a quiet laptop and up to 12 minutes on a busy one.

## What if name detection is off?
It depends on a spaCy model. If the model cannot load, person names are not detected and the PII count drops from 68 to 66. We hit this on two machines, fixed the loader, and the dashboard and reports now say when names are off.

## How is it tested?
Over 40 automated checks (Python and the dashboard). The suite includes an end-to-end test, a test that the library, command line and API agree, and tests for every PII rule. Rules that changed behaviour were checked by breaking them on purpose and confirming a test fails.

## What is not done?
OCR for scans, NeMo's own GPU dedup, hand-checking the NeMo-only removals, and model training (out of scope). The list is in `STATUS.md`.

## How would we use it on our own documents?
```bash
python -m pipeline.cli run my_pdfs/ -o out/       # or: bfsi-curate run my_pdfs/ -o out/
```
It writes `out/curated.jsonl` and `out/pipeline_summary.json`. From Python: `from pipeline.api import curate`.
