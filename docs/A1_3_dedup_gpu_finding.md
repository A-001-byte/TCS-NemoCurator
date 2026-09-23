# A1.3 — Real NeMo Curator Dedup: GPU Requirement Confirmed

## Finding
Both `nemo_curator.stages.deduplication.exact` and
`nemo_curator.stages.deduplication.fuzzy` fail on import with
`ModuleNotFoundError: No module named 'cudf'` on this CPU-only machine.

This contradicts NVIDIA's own docs table, which lists exact-dedup GPU
requirement as "Optional" -- in the actual installed 1.3.0 package,
`ExactDuplicateIdentification` unconditionally imports `cudf` at module
load time. Fuzzy dedup's GPU requirement is correctly documented as
"Required" and is confirmed the same way (cudf import inside
`connected_components.py`).

## Conclusion
Real Curator dedup is not achievable on this CPU-only dev machine, for
either exact or fuzzy phases -- not slow, a hard import failure.

## What we already have instead
Our existing `pipeline/dedup.py` implements the same algorithmic approach
Curator's GPU path uses: SHA-256 exact-hash matching, then MinHash/LSH
fuzzy matching (same shingle-based technique). This is a genuine
equivalent-logic implementation of the same method, not a different
approach -- the gap here is compute (GPU vs CPU), not algorithm design.

## Recommendation
Do not sink further time forcing cudf/RAPIDS onto CPU hardware for this
project cycle. Document as a known, verified constraint; revisit only if
GPU access becomes available to the team.
