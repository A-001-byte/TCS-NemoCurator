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
Our existing `pipeline/dedup.py` uses the same underlying primitive Curator's
GPU path does -- SHA-256 exact-hash matching, then MinHash/LSH shingle-based
similarity for the fuzzy phase -- but the two differ in resolution strategy,
not just compute. Curator's fuzzy path builds a similarity graph and finds
connected components (a global, transitive clustering: A~B~C get grouped even
if only A~B and B~C are direct matches). Ours is a greedy sequential pass --
each chunk is checked against already-kept chunks and dropped on first match,
with no clustering step. These can disagree on which representative survives
a near-duplicate cluster, and possibly on cluster membership itself for chains
of pairwise-but-not-mutual similarity. Similar technique, different algorithm;
GPU vs CPU is a separate, additional gap on top of that, not the only one.

## Recommendation
Do not sink further time forcing cudf/RAPIDS onto CPU hardware for this
project cycle. Document as a known, verified constraint; revisit only if
GPU access becomes available to the team.
