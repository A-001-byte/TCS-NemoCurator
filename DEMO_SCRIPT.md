# TCS NemoCurator — Demo Script

## 1. Start the application
Open two VS Code terminals from the project root.

Terminal 1 — start the Python API:
```powershell
py -m pipeline.server
```

Terminal 2 — start the dashboard:
```powershell
cd dashboard
npm.cmd run dev
```

Open the local URL printed by Vite in your browser.

## 2. Demonstration flow
1. Introduce NemoCurator as a pipeline for cleaning, deduplicating, quality-filtering, and curating regulatory/KYC documents.
2. Show the dashboard overview and its available pipeline statistics.
3. Explain that the current snapshot contains 3,325 curated chunks.
4. Show the document-type and token-related panels if available in the current UI.
5. Demonstrate the snapshot refresh control and wait for the refresh result.
6. Explain that PII redaction is part of the pipeline. The current summary reports 66 redacted entities.
7. Conclude by explaining that the pipeline records removals and quality statistics so its output can be inspected.

## 3. Data accuracy note
The current pipeline summary reports 35 input PDFs, 34 successfully extracted documents, and one extraction failure: `bank_of_baroda_aml_questionnaire.pdf` (empty extraction). Do not claim that all 35 PDFs were successfully processed.

## 4. End the demo
Show the final dashboard state and mention any known limitations honestly. Stop the frontend and backend with Ctrl+C in their respective terminals.
