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
