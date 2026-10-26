# SETUP.md — Real NeMo Curator environment (Stream A)

## Why not native Windows
Native pip install fails: fasttext/cosmos-xenna wheel builds require
Microsoft Visual C++ 14.0, not present on dev machines.
See logs/nemo_curator_install.log for the exact error.

## Working setup: WSL2 Ubuntu 22.04

1. wsl --install -d Ubuntu-22.04   (PowerShell, admin), reboot, create user
2. Inside WSL2:
   sudo apt update
   sudo apt install -y build-essential python3.11 python3.11-venv python3.11-dev python3-pip git
3. git clone https://github.com/A-001-byte/TCS-NemoCurator.git
   cd TCS-NemoCurator
4. python3.11 -m venv venv-curator
   source venv-curator/bin/activate
   pip install --upgrade pip
   pip install "nemo-curator[text_cpu]"

## Gotcha that cost real time
fasttext failed even inside WSL2 with:
  fatal error: Python.h: No such file or directory
Root cause: python3.11-dev (headers) is NOT pulled in by python3.11 alone
on Ubuntu. Fix: install python3.11-dev explicitly BEFORE pip install
(see step 2 above) to avoid the failed build + retry cycle.

## Verified working
pip show nemo-curator -> Version: 1.3.0

A0.3 quickstart verified against NVIDIA's official Text Quickstart
(https://docs.nvidia.com/nemo/curator/get-started/text), confirmed to
match installed version 1.3.0 (docs show "Latest · v1.3.0 (26.07)").
Ran a 2-line JSONL through Pipeline -> JsonlReader -> ScoreFilter
(WordCountFilter, NonAlphaNumericFilter) -> JsonlWriter. Short document
was correctly filtered out; long document passed through with computed
word_count and non_alpha_score fields attached. CPU-only, no GPU needed
for this stage (WordCountFilter/NonAlphaNumericFilter are heuristic,
not GPU classifiers).

## To resume work after a shutdown
wsl -d Ubuntu-22.04
cd ~/TCS-NemoCurator
source venv-curator/bin/activate

## venv-pii torch pin (update)
torch 2.14.0 (both default and +cpu build) has a genuine internal bug:
  ValueError: Duplicate dispatch rule for <built-in function intern>
Happens on gliner import regardless of transformers version (confirmed with
both 4.55.0 and 5.16.1 -- ruled out transformers as the cause). Root cause
is torch itself. Fix: pin torch==2.5.1 (CPU build via
--index-url https://download.pytorch.org/whl/cpu, avoids pulling
unnecessary CUDA toolkit packages on this GPU-less machine).

venv-pii final known-good stack:
  torch==2.5.1+cpu
  transformers==4.55.0
  gliner (installed --no-deps to avoid re-upgrading transformers)

## Main pipeline setup (Ubuntu 22.04, WSL2 or native Linux)

Confirmed working on Ubuntu 22.04.5 (WSL2), 20-25 Oct 2026.

1. Clone the repo:
   git clone https://github.com/A-001-byte/TCS-NemoCurator.git
   cd TCS-NemoCurator

2. Create and activate the venv:
   python3.11 -m venv venv-curator
   source venv-curator/bin/activate

3. Install dependencies:
   pip install --upgrade pip
   pip install -r requirements.txt

4. Verify:
   python3 -m pipeline.test_server
   # must print: ok: 8 chunks, 5 PII entities redacted

5. Run the full pipeline:
   python3 -m pipeline.run

## Resuming work after a shutdown
cd ~/TCS-NemoCurator
source venv-curator/bin/activate

## Notes
- Note: use `python3`, not `python`; it is not aliased on Ubuntu/Debian by default.
- GPU is optional. Automatic CUDA detection with CPU fallback (pipeline/device.py) applies to
  the quality classifier only (pipeline/quality.py, used when the optional DeBERTa classifier
  runs). Every other stage, including deduplication, runs on the CPU. GPU deduplication is not
  claimed: cuDF installs and runs on an RTX 4050, but the NeMo dedup import and runtime checks
  have not passed yet (docs/team/evidence/gpu_benchmark.md). Override with CURATOR_DEVICE=cpu|cuda.

## Verified install (26 Oct 2026, Ubuntu 22.04 on WSL2)

CPU install with tests:

    python3.11 -m venv venv-curator
    source venv-curator/bin/activate
    pip install --upgrade pip
    pip install -r requirements-dev.txt
    python3 -m pipeline.test_server
    python3 -m pipeline.test_device
    python3 -m pytest -q

Expected: `ok`, `ok`, then `29 passed`. Use `requirements.txt` instead if you do not need the tests.

Notes:
- torch pulls in the NVIDIA CUDA libraries even on a CPU-only machine. The download is large, so install once while online.
- GPU: on a machine with an NVIDIA GPU and driver, run `pip install -r requirements-gpu.txt`. The default pipeline still runs on CPU. The GPU is used only by the optional GLiNER and DeBERTa models (see docs/team/evidence/gpu_benchmark.md). Override with `CURATOR_DEVICE=cpu` or `CURATOR_DEVICE=cuda`.
- The real NeMo GPU dedup has not been run yet (see gpu_benchmark.md).
- tiktoken may download its encoding on first use, so run the token statistics once while online.
- WSL: if git says "Could not resolve host", run `echo "nameserver 8.8.8.8" | sudo tee /etc/resolv.conf` (it resets when WSL restarts).
