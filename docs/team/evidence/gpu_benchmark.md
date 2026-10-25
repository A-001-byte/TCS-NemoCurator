# GPU dedup check (B4)

**Date:** 25 Oct 2026
**Status:** partial. cuDF verified on the RTX 4050, real NeMo dedup run pending.

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
- CPU vs CUDA timing (Kunal's K4 task)

## Aditi's machine
No GPU visible in WSL (nvidia-smi not found), so the run has to happen on Kunal's laptop.

## Results
None recorded yet. Do not quote timings until measured.
