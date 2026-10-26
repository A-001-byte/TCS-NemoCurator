"""K4 default-pipeline CPU/CUDA setting benchmark, five PDFs and three runs."""
import json
import os
import statistics
import time
from pathlib import Path

import torch

from pipeline import api, pii, quality, run

PDFS = (
    "bank_of_baroda_kyc.pdf",
    "fiu_india_rbi_ctr_circular_2010.pdf",
    "rbi_kyc_summary_banklaw1.pdf",
    "rbi_kyc_fidcindia_aug2025.pdf",
    "rbi_kyc_updated_aug2025_allinonebanking.pdf",
)
ROOT = Path(__file__).resolve().parents[1]

def main():
    if pii.USE_GLINER_PII or quality.QUALITY_SIGNAL_MODE != "off" or quality.USE_REAL_QUALITY_CLASSIFIER:
        raise RuntimeError("Default CPU-only stages must be selected")
    files = [(name, (ROOT / "data/raw" / name).read_bytes()) for name in PDFS]
    pii._load_spacy()
    torch.cuda.init()
    original_stages = run.STAGES
    data = {}
    try:
        for mode in ("cpu", "cuda"):
            os.environ["CURATOR_DEVICE"] = mode
            runs = []
            for _ in range(3):
                stage_seconds = {}
                def timed(name, fn, sink=stage_seconds):
                    def wrapped():
                        start = time.perf_counter()
                        try:
                            return fn()
                        finally:
                            sink[name] = round(time.perf_counter() - start, 4)
                    return wrapped
                run.STAGES = [(name, timed(name, fn)) for name, fn in original_stages]
                result, _log = api.run_isolated(files=files)
                if result is None:
                    raise RuntimeError(f"Pipeline failed with {mode}: {_log[-2000:]}")
                runs.append({
                    "stage_seconds": stage_seconds,
                    "total_seconds": round(sum(stage_seconds.values()), 4),
                    "output_chunks": result["summary"]["final_output_chunks"],
                    "pii_entities": result["summary"]["pii_entities_redacted"],
                })
            data[mode] = {
                "runs": runs,
                "median_seconds": {stage: round(statistics.median(r["stage_seconds"][stage] for r in runs), 4) for stage, _ in original_stages},
                "median_total_seconds": round(statistics.median(r["total_seconds"] for r in runs), 4),
            }
    finally:
        run.STAGES = original_stages
        os.environ.pop("CURATOR_DEVICE", None)
    print(json.dumps({
        "benchmark": "default pipeline, quality signal off, GLiNER off",
        "pdfs": PDFS,
        "torch": torch.__version__,
        "gpu": torch.cuda.get_device_name(0),
        "runs_per_mode": 3,
        "cpu": data["cpu"],
        "cuda_setting": data["cuda"],
    }, indent=2))

if __name__ == "__main__":
    main()
