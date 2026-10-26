"""Self-check for pipeline.device — runs with no real GPU needed.
Fakes torch so we can test all branches: auto/cpu/cuda/env-override/crash/missing-torch.
"""
import contextlib
import os
import sys
import tempfile
import types
from pathlib import Path

_ABSENT = object()
_PRIOR_TORCH = []  # the sys.modules["torch"] entry found by each _install_fake_torch, restored in order


@contextlib.contextmanager
def _curator_device_env(value=None):
    """Set CURATOR_DEVICE to `value` (or clear it) inside the block, then put back what was there."""
    previous = os.environ.get("CURATOR_DEVICE")
    if value is None:
        os.environ.pop("CURATOR_DEVICE", None)
    else:
        os.environ["CURATOR_DEVICE"] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("CURATOR_DEVICE", None)
        else:
            os.environ["CURATOR_DEVICE"] = previous


def _install_fake_torch(cuda_available, device_name="Fake GPU", raise_on_check=False):
    """Replace sys.modules['torch'] with a fake module for this test."""
    fake = types.ModuleType("torch")
    fake_cuda = types.SimpleNamespace()

    def is_available():
        if raise_on_check:
            raise RuntimeError("simulated crash in cuda detection")
        return cuda_available

    def get_device_name(idx=0):
        return device_name

    fake_cuda.is_available = is_available
    fake_cuda.get_device_name = get_device_name
    fake.cuda = fake_cuda
    _PRIOR_TORCH.append(sys.modules.get("torch", _ABSENT))
    sys.modules["torch"] = fake


def _remove_fake_torch():
    """Undo the matching _install_fake_torch: restore the torch that was there before, or drop
    the fake if there was none. Does nothing when no fake is installed."""
    if not _PRIOR_TORCH:
        return
    prior = _PRIOR_TORCH.pop()
    if prior is _ABSENT:
        sys.modules.pop("torch", None)
    else:
        sys.modules["torch"] = prior


def _reload_device():
    sys.modules.pop("pipeline.device", None)
    import pipeline.device as device
    return device


def test_auto_picks_cpu_when_no_cuda():
    _install_fake_torch(cuda_available=False)
    try:
        device = _reload_device()
        assert device.pick("auto") == "cpu", "expected cpu when CUDA unavailable"
    finally:
        _remove_fake_torch()


def test_auto_picks_cuda_when_available():
    _install_fake_torch(cuda_available=True)
    try:
        with _curator_device_env(None):  # an outside CURATOR_DEVICE must not decide this test
            device = _reload_device()
            assert device.pick("auto") == "cuda:0", "expected cuda:0 when CUDA available"
    finally:
        _remove_fake_torch()


def test_env_override_forces_cpu():
    _install_fake_torch(cuda_available=True)
    os.environ["CURATOR_DEVICE"] = "cpu"
    try:
        device = _reload_device()
        assert device.pick("auto") == "cpu", "env override to cpu failed"
    finally:
        os.environ.pop("CURATOR_DEVICE", None)
        _remove_fake_torch()


def test_env_override_forces_cuda():
    _install_fake_torch(cuda_available=True)
    os.environ["CURATOR_DEVICE"] = "cuda"
    try:
        device = _reload_device()
        assert device.pick("auto") == "cuda:0", "env override to cuda failed"
    finally:
        os.environ.pop("CURATOR_DEVICE", None)
        _remove_fake_torch()


def test_crash_in_detection_falls_back_to_cpu():
    _install_fake_torch(cuda_available=True, raise_on_check=True)
    try:
        device = _reload_device()
        assert device.pick("auto") == "cpu", "crash during detection must fall back to cpu"
    finally:
        _remove_fake_torch()


def test_missing_torch_falls_back_to_cpu():
    _remove_fake_torch()
    # Simulate torch not being installed at all by blocking the import
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "torch":
            raise ImportError("no module named torch (simulated)")
        return real_import(name, *args, **kwargs)

    import builtins
    builtins.__import__ = blocked_import
    try:
        device = _reload_device()
        assert device.pick("auto") == "cpu", "missing torch must fall back to cpu"
    finally:
        builtins.__import__ = real_import


def test_describe_cpu():
    _remove_fake_torch()
    device = _reload_device()
    assert device.describe("cpu") == "cpu"


def test_describe_cuda_with_fake_gpu_name():
    _install_fake_torch(cuda_available=True, device_name="NVIDIA GeForce RTX 4050 Laptop GPU")
    try:
        device = _reload_device()
        result = device.describe("cuda:0")
        assert "cuda:0" in result and "RTX 4050" in result, f"unexpected describe output: {result}"
    finally:
        _remove_fake_torch()


def test_quality_record_reports_cpu_unless_the_classifier_ran():
    from pipeline import quality
    from pipeline.test_quality_signal import GOOD, run_quality

    _install_fake_torch(cuda_available=True, device_name="Fake GPU")  # a GPU is visible all the same
    try:
        with tempfile.TemporaryDirectory() as tmp:
            # default run: heuristics only, nothing ran on the GPU
            _, record, _ = run_quality(Path(tmp), [GOOD], "off", lambda text: "High")
            assert record["device"] == "cpu", record["device"]
            # a run whose classifier produced labels reports the device the model sits on
            quality._classifier_device = "cuda:0"  # what _load_quality_classifier sets
            _, record, calls = run_quality(Path(tmp), [GOOD], "model", lambda text: "High")
            assert calls == 1 and record["device"] == "cuda:0 (Fake GPU)", record["device"]
            # the same chunk again is a cache hit: no inference, so back to cpu
            _, record, calls = run_quality(Path(tmp), [GOOD], "model", lambda text: "High")
            assert calls == 0 and record["device"] == "cpu", record["device"]
    finally:
        quality._classifier_device = None
        _remove_fake_torch()


def main():
    tests = [
        test_auto_picks_cpu_when_no_cuda,
        test_auto_picks_cuda_when_available,
        test_env_override_forces_cpu,
        test_env_override_forces_cuda,
        test_crash_in_detection_falls_back_to_cpu,
        test_missing_torch_falls_back_to_cpu,
        test_describe_cpu,
        test_describe_cuda_with_fake_gpu_name,
        test_quality_record_reports_cpu_unless_the_classifier_ran,
    ]
    for t in tests:
        t()
    print("ok: pick() and describe() behave correctly under auto/cpu/cuda/env-override/crash/missing-torch")


if __name__ == "__main__":
    main()
