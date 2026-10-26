# Setup

How to install the pipeline on Linux (native Ubuntu, or WSL2 on Windows), run the checks, and add the optional parts.
The default pipeline needs only Python and the packages in `requirements.txt`; it runs on the CPU and does not need a GPU, torch or NeMo.

Which file installs what:

| File | Adds | When you need it |
|---|---|---|
| `requirements.txt` | the whole default pipeline (no torch, no NeMo) | always |
| `requirements-dev.txt` | pytest, coverage, ruff | to run the tests |
| `requirements-ml.txt` | torch, transformers, GLiNER | the optional PII model and the quality classifier |
| `requirements-gpu.txt` | the above plus cuDF | a machine with an NVIDIA GPU and driver |
| `requirements-nemo.txt` | real NeMo Curator 1.3.0 | `pipeline/nemo_compare.py` only; Linux or WSL2 only |

## 1. Prepare the machine

Ubuntu 22.04 or 24.04. Python 3.11 or newer is required (22.04 ships 3.10, so install 3.11; 24.04 ships 3.12 and works as is).

On Windows, use WSL2:

```powershell
wsl --install -d Ubuntu-22.04        # PowerShell as administrator, then reboot and create a user
```

Inside Ubuntu:

```bash
sudo apt update
sudo apt install -y build-essential python3.11 python3.11-venv python3.11-dev python3-pip git
```

`python3.11-dev` matters. Without it the NeMo install fails while building `fasttext` with `fatal error: Python.h: No such file or directory`; Ubuntu does not pull the headers in with `python3.11` alone. Install it before any `pip install`.

Native Windows cannot install NeMo Curator (`fasttext` and `cosmos-xenna` need the Microsoft C++ build tools; the error is in `docs/archive/logs/nemo_curator_install.log`). The default pipeline, tests and dashboard do run on Windows.

## 2. Install and check (CPU)

```bash
git clone https://github.com/A-001-byte/TCS-NemoCurator.git
cd TCS-NemoCurator
python3.11 -m venv venv-curator
source venv-curator/bin/activate
pip install --upgrade pip
pip install -r requirements-dev.txt          # use requirements.txt if you do not need the tests
python3 -m pytest -q                         # every test must pass; no network is needed
```

Use `python3` (not `python`) on Ubuntu; `python` is not defined there by default. The tests cover the library, the terminal command and the HTTP server. They need no GPU and no model download.

Then run the whole corpus (the 35 PDFs in `data/raw/`):

```bash
python3 -m pipeline.run                      # about 5.5 minutes on a quiet CPU, up to about 12 on a busy one
```

Expected on the reference corpus: 35 PDFs in, 34 readable (one is a scan), 3,726 chunks into dedup, 3,396 after, **3,325 final**, **68 PII items**, name detection on, `quality_filter` device `cpu`. These numbers are checked against `dashboard/public/pipeline_summary.json`. If the PII count is 66, person-name detection is off (the spaCy model did not load): reinstall with `pip install -r requirements.txt` and look for the "name detection off" warning.

Other ways to use it (the library, `bfsi-curate`, the HTTP API) are in the README. To install the terminal command: `pip install -e .`.

## 3. The dashboard

Needs Node.js 20.19 or newer (22.12 or newer on the 22 line); CI uses 22. Ubuntu 22.04's own `nodejs` package is version 12 and is too old, so install a current Node from nodejs.org, or run the dashboard on Windows and point it at the server in WSL (WSL's port 8000 is reachable from Windows as `127.0.0.1:8000`, which is what the dashboard's proxy uses).

```bash
python3 -m pipeline.server                   # terminal 1: API on 127.0.0.1:8000
cd dashboard && npm install && npm run dev   # terminal 2: open the address it prints
```

The dashboard reads the snapshots in `dashboard/public/`; its refresh button (or `POST /api/refresh`) re-runs the corpus and rewrites them. For one-command startup in WSL/Linux, use the project environment's Python:

```bash
CURATOR_PYTHON="$HOME/nemo-kunal-venv313/bin/python" ./scripts/start_local.sh
```

The launcher starts both local servers on 127.0.0.1; Ctrl+C stops both. Replace the Python path with your own environment, or activate it first and omit `CURATOR_PYTHON`. Before refreshing the corpus or processing uploaded PDFs, choose **quality labels off/on** and **Auto/CPU/GPU** in the dashboard. Defaults are labels off and Auto, preserving the standard regex + spaCy PII run. The model device selector becomes available when labels are on. Auto uses CUDA when available; an explicit GPU request fails clearly if CUDA is unavailable. The saved snapshot shows the quality stage's actual device, not just the GPU detected on the machine. A failed run does not replace the previous snapshot.

Headless refreshes can still set `CURATOR_REFRESH_DEVICE=cuda CURATOR_REFRESH_QUALITY_SIGNAL=model` on the API server. The server has no authentication, so it listens on loopback only unless you pass `--host` or set `CURATOR_HOST`.

## 4. GPU (optional)

The default pipeline always runs on the CPU. The GPU is used only by two optional models, GLiNER (PII) and the DeBERTa quality label, and the automatic choice of device (`pipeline/device.py`) applies to both optional models. GPU deduplication is **not** claimed: cuDF installs and runs on an RTX 4050, but the real NeMo dedup import and runtime check has not passed yet (`docs/team/evidence/gpu_benchmark.md`).

On a machine with an NVIDIA GPU and driver (inside WSL2, `nvidia-smi` must work first):

```bash
source venv/bin/activate
python -m pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cu126
python -m pip install -r requirements-ml.txt
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"  # True
bfsi-curate run data/raw -o out-gpu --device cuda --pii-engine gliner --quality-signal model
```

This installs the optional model dependencies once in the active environment. Repeat only the last command for later runs. Use `requirements-gpu.txt` only if you also need cuDF; the optional PII and quality models do not need it. `--pii-engine gliner` replaces regex + spaCy and does not apply all of its cross-field checks. `--quality-signal model` adds a DeBERTa label to each surviving chunk; it does not filter chunks. Model weights download on first use and are cached. `--device cuda` fails clearly if CUDA-enabled PyTorch is absent. The run's summary records the PII engine and quality model device.

Notes:
- torch pulls in the NVIDIA CUDA libraries even on a CPU-only machine. The download is large, so install it once while online.
- torch 2.14.0 failed on one CPU build with `ValueError: Duplicate dispatch rule for <built-in function intern>` when importing `gliner`. Changing `transformers` did not help. If you hit it, install `torch==2.5.1` (for a CPU-only machine from `--index-url https://download.pytorch.org/whl/cpu`) and keep `transformers==4.55.0`.
- `tiktoken` downloads its encoding on first use, so run the token statistics once while online.

## 5. Real NeMo Curator (optional)

Only `pipeline/nemo_compare.py` needs it; the pipeline never imports it. Use a separate virtual environment:

```bash
python3.11 -m venv venv-nemo
source venv-nemo/bin/activate
pip install --upgrade pip
pip install -r requirements-nemo.txt
pip show nemo-curator                        # Version: 1.3.0
python3 -m pipeline.nemo_compare data/deduped/chunks.jsonl data/output/curated.jsonl dashboard/public/nemo_comparison.json
```

Run `python3 -m pipeline.run` first so the two input files exist. The comparison follows NVIDIA's official text quickstart for 1.3.0 (`Pipeline`, `JsonlReader`, `ScoreFilter`, `JsonlWriter`) on the CPU executor; no GPU is needed.

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| `Python.h: No such file or directory` during `pip install` | `sudo apt install python3.11-dev`, then repeat the install |
| `python: command not found` | use `python3` |
| PII count 66 instead of 68 | name detection is off; reinstall `requirements.txt`, check the spaCy model loaded |
| `git clone` says "Could not resolve host" in WSL | `echo "nameserver 8.8.8.8" \| sudo tee /etc/resolv.conf` (it resets when WSL restarts) |
| `POST /api/run` answers 409 | another run or refresh is in progress; wait for it |
| `bfsi-curate` not found | `pip install -e .` in the active virtual environment |

## Resuming after a shutdown

```bash
wsl -d Ubuntu-22.04                          # on Windows
cd ~/TCS-NemoCurator
source venv-curator/bin/activate
```

## Verified

Ubuntu 22.04.5 on WSL2, Python 3.11, 20 to 26 Oct 2026 (`docs/team/evidence/linux_run.md`): the full run matched the Windows run at every stage. The fresh-install check from `requirements-dev.txt` passed all tests; CI repeats it on Ubuntu for every pull request.

Fresh clone, 27 Oct 2026, installed exactly as above:

| Machine | Tests | Full run (CPU) | Result |
|---|---|---|---|
| WSL2, Ubuntu 22.04, 12 cores, 7.6 GB | 214 passed in 43 s | 4 min 18 s | 34 of 35 readable, 3,325 chunks, 68 PII items |
| VMware VM, Ubuntu 24.04, Python 3.12, 6 virtual cores | 209 passed in 171 s | 40 min 30 s | identical |

Both give a `curated.jsonl` with SHA-256 starting `0c238547804a8407`, the same as Windows. The VM is correct but about nine times slower; use WSL2 or native Linux for a demonstration. The server answered `/api/health`, a 400 for an empty run and a 405 for a wrong method, and a one-PDF upload through the API and through the dashboard returned 10 chunks in about 3 seconds.
