# GPU dedup check (B4)

**Date:** 25 Oct 2026
**Status:** B4 partial (real NeMo dedup pending); K4 measurements completed below.

## Why this matters
docs/A1_3_dedup_gpu_finding.md found that real NeMo Curator dedup (exact and fuzzy) fails on import with `No module named 'cudf'` on a CPU-only machine.

## Verified (reported by Kunal, RTX 4050, WSL2)
- nvidia-smi detects the GPU
- `cudf-cu12==26.10.2` installs (pinned in requirements-gpu.txt)
- `cudf.Series([1, 2, 3])` runs and prints the expected output
- This was in WSL, not his VMware VM

## Not yet done
- Import check of nemo_curator.stages.deduplication.exact and .fuzzy on the GPU machine
- A real NeMo dedup run on the 35-PDF corpus

## Aditi's machine
No GPU visible in WSL (nvidia-smi not found), so the run has to happen on Kunal's laptop.

## B4 results
Real NeMo dedup timings are not recorded yet. K4 optional-model timings are below.

## K4: CPU vs CUDA on Kunal's RTX 4050

**Measured:** 25 Oct 2026 in Kali WSL2 (kernel 6.6.87.2-microsoft-standard-WSL2). GPU: NVIDIA GeForce RTX 4050 Laptop GPU, 6141 MiB (6 GB), driver 616.64. Python 3.13.12; PyTorch 2.14.0+cu126 (CUDA runtime 12.6); transformers 4.55.0; GLiNER 0.2.25; spaCy 3.8.16. Optional model runs used four CPU threads.

### Workload and method

The same five PDFs were used for every comparison: `bank_of_baroda_kyc.pdf`, `fiu_india_rbi_ctr_circular_2010.pdf`, `rbi_kyc_summary_banklaw1.pdf`, `rbi_kyc_fidcindia_aug2025.pdf`, and `rbi_kyc_updated_aug2025_allinonebanking.pdf`. For each optional model, the script extracted four non-overlapping 80-word samples from each PDF (20 samples total). It loaded the model and warmed up one inference before timing, set `CURATOR_DEVICE=cpu` or `cuda`, verified model placement, and made three timed passes over the same texts on each device. CUDA was synchronized around every timed pass. Times exclude PDF extraction, model download/loading, and initialization. The classifier used the actual `pipeline.quality._classifier_label` path; GLiNER used `pipeline.pii.redact_pii_gliner` including overlap handling and replacement. No model outputs contained in this report expose source text.

| Optional stage (20 samples) | CPU runs (s) | CPU median (s) | CUDA runs (s) | CUDA median (s) | Inference speedup |
|---|---:|---:|---:|---:|---:|
| GLiNER PII + redaction | 24.0850, 20.6055, 21.3758 | **21.3758** | 1.3801, 1.3216, 1.2886 | **1.3216** | **16.17×** |
| DeBERTa quality signal | 4.9242, 4.8454, 5.6968 | **4.9242** | 0.5872, 0.5338, 0.4833 | **0.5338** | **9.22×** |

The GLiNER model reported `cpu` and `cuda:0` placement as requested. Its redacted output SHA-256 was identical across all six passes; each pass found eight entities in these samples. The quality classifier also produced the same 20 labels on both devices (8 Low, 11 Medium, 1 High). Peak PyTorch CUDA memory allocated was 1765.6 MiB for GLiNER and 741.6 MiB for DeBERTa; this excludes CUDA context and allocator overhead.

### Default pipeline: per-stage timings

The normal pipeline keeps `USE_GLINER_PII=False`, `QUALITY_SIGNAL_MODE=off`, and `USE_REAL_QUALITY_CLASSIFIER=False`. It runs regex + spaCy PII and heuristic quality rules on CPU. For this separate check, each of the five complete PDFs went through the isolated pipeline three times with each `CURATOR_DEVICE` setting. The spaCy model was loaded before timing. Times below are medians of each stage's three runs; the total median is computed from whole-run stage sums and therefore need not equal the sum of stage medians. Every run produced 122 final chunks and seven redacted PII entities.

| Default stage | CPU median (s) | CUDA setting median (s) |
|---|---:|---:|
| PDF extraction | 7.4980 | 8.2435 |
| Clean + language ID | 0.0477 | 0.0526 |
| Heal | 0.6802 | 0.7576 |
| Dedup | 0.2892 | 0.3322 |
| Heuristic quality filter | 0.0615 | 0.0630 |
| Regex + spaCy PII redaction | 2.6728 | 3.0791 |
| Output | 0.0040 | 0.0047 |
| **Total stage time, median of run totals** | **11.2523** | **12.4692** |

Whole-run stage-time observations were CPU **15.5545, 9.6736, 11.2523 s** and CUDA setting **12.4692, 10.4224, 14.6515 s**. These default stages do not execute model inference on CUDA. Their differences reflect normal run-to-run variance, especially PDF extraction; there is **no measured whole-pipeline GPU speedup**. The optional GLiNER and DeBERTa inference stages got faster on GPU only when enabled. This K4 comparison does not complete the separate real NeMo GPU dedup check described in B4 above.

### Reproduce

In the Kali WSL repository with the optional dependencies and both model weights available:

```bash
PYTHONPATH=. python scripts/benchmark_gpu_pipeline.py
PYTHONPATH=. python scripts/benchmark_gpu_gliner.py
PYTHONPATH=. python scripts/benchmark_gpu_quality.py
```

Each script sets and checks the relevant device selection. The two model scripts emit JSON with all raw timings and output checks. GLiNER is moved to `pipeline.device.pick()` in `pipeline/pii.py`; without that placement, selecting CUDA would still leave GLiNER on CPU. The normal pipeline flags remain off by default.
