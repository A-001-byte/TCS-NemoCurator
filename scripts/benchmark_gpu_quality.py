"""K4 CPU/CUDA benchmark of the optional DeBERTa quality signal."""
import json
import os
import platform
import statistics
import time
from collections import Counter
from pathlib import Path

import torch

from pipeline import quality
from pipeline.device import pick
from pipeline.extract import extract_pdf_text

PDFS = (
    "bank_of_baroda_kyc.pdf",
    "fiu_india_rbi_ctr_circular_2010.pdf",
    "rbi_kyc_summary_banklaw1.pdf",
    "rbi_kyc_fidcindia_aug2025.pdf",
    "rbi_kyc_updated_aug2025_allinonebanking.pdf",
)
ROOT = Path(__file__).resolve().parents[1]
RUNS = 3

def samples():
    texts = []
    for name in PDFS:
        words = extract_pdf_text(ROOT / "data/raw" / name).split()
        if len(words) < 320:
            raise ValueError(f"Too few words in {name}: {len(words)}")
        texts.extend(" ".join(words[i:i+80]) for i in range(0, 320, 80))
    return texts

def measure(device, texts):
    os.environ["CURATOR_DEVICE"] = device.type
    assert pick() == str(device)
    quality._classifier_model.to(device)
    quality._classifier_device = device
    if device.type == "cuda":
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
    quality._classifier_label(texts[0])  # warm up outside timing
    times = []
    runs = []
    for _ in range(RUNS):
        if device.type == "cuda":
            torch.cuda.synchronize()
        start = time.perf_counter()
        labels = [quality._classifier_label(text) for text in texts]
        if device.type == "cuda":
            torch.cuda.synchronize()
        times.append(round(time.perf_counter() - start, 4))
        runs.append(labels)
    if not all(run == runs[0] for run in runs):
        raise RuntimeError(f"Unstable classifier labels on {device}")
    return {
        "seconds": times,
        "median_seconds": round(statistics.median(times), 4),
        "labels": runs[0],
        "label_counts": dict(Counter(runs[0])),
        "peak_cuda_memory_mib": round(torch.cuda.max_memory_allocated()/1024**2, 1) if device.type == "cuda" else None,
    }

def main():
    torch.set_num_threads(4)
    texts = samples()
    quality._load_quality_classifier()
    cpu = measure(torch.device("cpu"), texts)
    cuda = measure(torch.device("cuda:0"), texts)
    os.environ.pop("CURATOR_DEVICE", None)
    print(json.dumps({
        "benchmark": "optional DeBERTa quality signal inference",
        "model": "nvidia/quality-classifier-deberta",
        "python": platform.python_version(),
        "torch": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0),
        "cpu_threads": torch.get_num_threads(),
        "pdfs": PDFS,
        "samples_per_pdf": 4,
        "words_per_sample": 80,
        "total_samples": len(texts),
        "runs_per_device": RUNS,
        "cpu": cpu,
        "cuda": cuda,
        "labels_match": cpu["labels"] == cuda["labels"],
        "speedup": round(cpu["median_seconds"]/cuda["median_seconds"], 2),
    }, indent=2))

if __name__ == "__main__":
    main()
