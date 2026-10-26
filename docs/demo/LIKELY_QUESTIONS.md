# NemoCurator — Likely Questions and Answers

## What does NemoCurator do?
It processes regulatory and KYC/AML documents through extraction, cleaning, deduplication, quality filtering, and PII redaction.

## How many source documents are available?
The current raw input folder contains 35 PDFs.

## Were all 35 PDFs processed successfully?
No. The latest summary reports 34 successful extractions and one failure: `bank_of_baroda_aml_questionnaire.pdf`, reported as empty extraction.

## How many curated chunks are in the current snapshot?
The current pipeline summary reports 3,325 final output chunks.

## Why is deduplication needed?
It removes repeated content and boilerplate so the curated dataset contains less redundant text.

## How is personally identifiable information handled?
The pipeline uses a regex-plus-SpaCy redaction stage. The current summary reports 66 redacted entities, including emails, pincodes, CINs, phone numbers, and a SWIFT/BIC identifier. Name detection is reported as unavailable, so this is not a guarantee that every possible PII type is detected.

## What does the quality filter do?
It removes chunks that fail configured text-quality checks, such as low alphabetic ratio, high symbol ratio, or low lexical diversity.

## What does the refresh control do?
It calls the backend refresh endpoint to regenerate the dashboard snapshots from the pipeline and then reloads the summary.

## What should be said about limitations?
Be transparent about the one failed PDF extraction and the fact that automated PII detection has limitations. Do not claim complete extraction or perfect redaction.

## How do you start the demo?
Run `py -m pipeline.server` from the project root in one terminal. In a second terminal, run `cd dashboard` and then `npm.cmd run dev`. Open the local URL shown by Vite.
