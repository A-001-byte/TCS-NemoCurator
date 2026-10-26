# Contributing

## Set up

```bash
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt # core requirements plus pytest, coverage and ruff
cd dashboard && npm ci               # the React dashboard (Node 22)
```

Other installs, each on top of the core file: `requirements-ml.txt` (the optional GLiNER and DeBERTa
models), `requirements-gpu.txt` (the same on an NVIDIA GPU), `requirements-nemo.txt` (real NeMo
Curator, only for `pipeline/nemo_compare.py`; Linux or WSL2). `SETUP.md` has the Linux walkthrough.

## Before you push

These are exactly what CI runs. All must pass.

```bash
ruff check pipeline tests scripts
ruff format --check pipeline tests scripts      # `ruff format pipeline tests scripts` fixes it
python -m pytest -q --cov                       # about 80 s; the coverage figure is printed at the end
cd dashboard && npm run lint && npm test && npm run build
```

## Rules of this repository

- **Never push to `main`, never force-push.** One change per branch, one pull request per change.
- **Behaviour rules need a test that fails when the rule is broken.** After writing the test, break the
  rule on purpose, confirm the test fails, and put it back. Say so in the pull request.
- **The two contracts are frozen.** A stage record is `{stage, docs_in, docs_out, removed, reason_counts}`
  and an output line is `{text, metadata}`. Fields may be added; none may be renamed or removed.
- **Numbers are generated, never typed.** After a change that affects results, run
  `python -m pipeline.refresh_snapshots` (all 35 PDFs, 6 to 12 minutes), then
  `python scripts/make_final_numbers.py`. Do not edit `dashboard/public/*.json` or
  `docs/FINAL_NUMBERS.md` by hand.
- **Say what you did not check.** A claim in a document or a pull request must match what was measured;
  state limits plainly (see `docs/IMPROVEMENT_LOG.md` for the tone).
- **No personal data in the repository.** `data/raw/` holds public documents only. Examples in snapshots
  and tests are masked or synthetic. See `SECURITY.md`.
- **Commit messages:** `type: what changed` (feat, fix, refactor, docs, test, chore, data), then a short
  body saying why.
- **Imports:** the core install has no `torch`. A top-level import of an optional package in
  `pipeline/` fails `tests/test_packaging.py`; import it inside the function that needs it.

## Where things live

| Folder | What |
|---|---|
| `pipeline/` | One module per stage, plus `api.py` (library), `cli.py`, `server.py`, `refresh_snapshots.py` |
| `tests/` and `pipeline/test_*.py` | pytest tests and the older self-check scripts (`python -m pipeline.test_x`) |
| `dashboard/` | React (Vite) dashboard; `src/sections/` has one file per section |
| `scripts/` | Benchmarks and `make_final_numbers.py` |
| `docs/` | Start at `docs/README.md` |
