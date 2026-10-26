# Documentation index

Start with the top-level `README.md` (what the project is and how to run it), `STATUS.md` (what is done and what is not) and `SETUP.md` (installing on Linux).

## Current state

| File | What it is |
|---|---|
| `FINAL_NUMBERS.md` | Every headline number, **generated** from the dashboard snapshots by `scripts/make_final_numbers.py`. The only source for slides. |
| `IMPROVEMENT_LOG.md` | Every change to the pipeline since the first working version, with before and after numbers and the decision behind each. |
| `FINALIZATION_LOOP.md` | The sequenced plan from "all tasks merged" to the release, with the evidence for each finished task. |

## Findings and evidence

| File | What it shows |
|---|---|
| `PII_RECALL.md` | **Generated** by `python -m pipeline.eval_pii`: how many PII values the rules hide on a labelled synthetic set, per type, with every miss and false alarm listed. |
| `A1_2_pii_gliner_comparison.md` | NVIDIA's GLiNER-PII model compared with our regex and spaCy rules. |
| `A1_3_dedup_gpu_finding.md` | Real NeMo Curator dedup needs a GPU (`cudf`); ours runs on the CPU. |
| `A1_4_quality_classifier_comparison.md` | Why NVIDIA's quality classifier is not used as a filter (about 17 times stricter, judges layout). |
| `evidence/stream-c/` | PII stage evidence: stage records, validation report, heal report. |
| `team/evidence/linux_run.md` | The full run on Ubuntu (WSL2) matches the Windows run. |
| `team/evidence/gpu_benchmark.md` | GPU against CPU for the optional models, measured on an RTX 4050. |
| `team/evidence/quality_review.md` | A held-out review of the quality filter and the regulatory tags. |

The task files each person was given (for example `04_KUNAL.md`, named in the evidence above) were handed out separately and are not kept in the repository.

## Demo

| File | What it is |
|---|---|
| `demo/DEMO_SCRIPT.md` | The 10-minute run of show, the pre-flight commands and the fallbacks. |
| `demo/LIKELY_QUESTIONS.md` | Likely questions with honest answers. |
| `team/backup/` | Dashboard screenshots to show if the live demo fails. |

## History

`archive/` holds the early planning papers, the blueprint and the install logs. It is kept for the record and is not maintained; see `archive/README.md`.
