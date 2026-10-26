"""K4 CPU/CUDA benchmark of optional GLiNER PII inference."""
import hashlib
import json
import os
import statistics
import time
from collections import Counter
import torch
from benchmark_gpu_quality import PDFS, samples
from pipeline import pii
from pipeline.device import pick

def measure(mode, texts):
    os.environ["CURATOR_DEVICE"] = mode
    device = pick()
    pii._gliner_model.to(device)
    if mode == "cuda":
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
    pii.redact_pii_gliner(texts[0], {}, [], "warmup")
    times = []
    signatures = []
    for _ in range(3):
        counts = Counter()
        examples = []
        if mode == "cuda":
            torch.cuda.synchronize()
        start = time.perf_counter()
        outputs = [pii.redact_pii_gliner(text, counts, examples, str(i))[0] for i, text in enumerate(texts)]
        if mode == "cuda":
            torch.cuda.synchronize()
        times.append(round(time.perf_counter() - start, 4))
        signatures.append((dict(counts), hashlib.sha256("\n".join(outputs).encode()).hexdigest()))
    return {
        "model_device": str(pii._gliner_model.device),
        "seconds": times,
        "median_seconds": round(statistics.median(times), 4),
        "counts": signatures[0][0],
        "redacted_sha256": signatures[0][1],
        "stable_across_runs": all(x == signatures[0] for x in signatures),
        "peak_cuda_memory_mib": round(torch.cuda.max_memory_allocated()/1024**2, 1) if mode == "cuda" else None,
    }

def main():
    torch.set_num_threads(4)
    texts = samples()
    os.environ["CURATOR_DEVICE"] = "cpu"
    pii._load_gliner()
    cpu = measure("cpu", texts)
    cuda = measure("cuda", texts)
    os.environ.pop("CURATOR_DEVICE", None)
    print(json.dumps({
        "benchmark": "optional GLiNER PII inference plus redaction",
        "model": "nvidia/gliner-PII",
        "gliner_version": __import__("importlib.metadata", fromlist=["version"]).version("gliner"),
        "torch": torch.__version__,
        "gpu": torch.cuda.get_device_name(0),
        "cpu_threads": torch.get_num_threads(),
        "pdfs": PDFS,
        "samples_per_pdf": 4,
        "words_per_sample": 80,
        "total_samples": len(texts),
        "runs_per_device": 3,
        "cpu": cpu,
        "cuda": cuda,
        "redactions_match": cpu["redacted_sha256"] == cuda["redacted_sha256"],
        "speedup": round(cpu["median_seconds"]/cuda["median_seconds"], 2),
    }, indent=2))

if __name__ == "__main__":
    main()
