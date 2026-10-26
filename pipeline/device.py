"""Automatic CPU/GPU device selection for the pipeline.

pick() never raises — any failure anywhere falls back to CPU.
"""

import os


def pick(requested: str = "auto") -> str:
    """Return 'cpu' or 'cuda:0'.

    'auto' uses CUDA if torch.cuda.is_available(), else CPU.
    Env var CURATOR_DEVICE=cpu|cuda overrides.
    Never raises: any failure means 'cpu'.
    """
    override = os.environ.get("CURATOR_DEVICE", "").strip().lower()
    if override in ("cpu", "cuda"):
        if override == "cpu":
            return "cpu"
        requested = "cuda"

    if requested not in ("auto", "cuda"):
        return "cpu"

    try:
        import torch

        if torch.cuda.is_available():
            return "cuda:0"
    except Exception:
        pass

    return "cpu"


def describe(device: str) -> str:
    """Human text for the dashboard, e.g. 'cuda:0 (NVIDIA GeForce RTX 4050 Laptop GPU)' or 'cpu'."""
    if not device or device == "cpu":
        return "cpu"

    try:
        import torch

        if device.startswith("cuda") and torch.cuda.is_available():
            idx = 0
            if ":" in device:
                idx = int(device.split(":", 1)[1])
            name = torch.cuda.get_device_name(idx)
            return f"{device} ({name})"
    except Exception:
        pass

    return device
