"""One background snapshot refresh at a time, with a status the dashboard can poll.

A refresh runs the whole pipeline (minutes), so the HTTP request that starts it must not wait for it.
`RefreshJob.start()` returns at once; `status()` says whether the job is idle, running, succeeded or
failed, and how long it has been running.
"""

import logging
import threading
import time
from datetime import datetime, timezone

log = logging.getLogger(__name__)

IDLE, RUNNING, SUCCEEDED, FAILED = "idle", "running", "succeeded", "failed"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RefreshJob:
    """Runs `run()` (which returns the published summary dict) in a thread, never two at once."""

    def __init__(self, run):
        self._run = run
        self._lock = threading.Lock()
        self._state = {"state": IDLE}
        self._started = 0.0

    def start(self, options: dict | None = None) -> bool:
        """Start the job with validated per-run options; refuse a concurrent refresh."""
        with self._lock:
            if self._state["state"] == RUNNING:
                return False
            self._state = {"state": RUNNING, "started_at": _now(), **(options or {})}
            self._started = time.monotonic()
        threading.Thread(target=self._work, args=(options or {},), name="snapshot-refresh", daemon=True).start()
        return True

    def status(self) -> dict:
        """A copy of the current state; `elapsed_seconds` is live while the job runs."""
        with self._lock:
            status = dict(self._state)
            if status["state"] == RUNNING:
                status["elapsed_seconds"] = round(time.monotonic() - self._started)
            return status

    def _work(self, options: dict) -> None:
        try:
            summary = self._run(**options)
        except Exception as exc:  # report any failure to the dashboard instead of losing it in a thread
            log.exception("snapshot refresh failed")
            self._finish({"state": FAILED, "error": f"{type(exc).__name__}: {exc}"})
        else:
            self._finish(
                {
                    "state": SUCCEEDED,
                    "chunks": summary.get("final_output_chunks"),
                    "pii_entities": summary.get("pii_entities_redacted"),
                }
            )

    def _finish(self, outcome: dict) -> None:
        with self._lock:
            elapsed = round(time.monotonic() - self._started)
            self._state = {**self._state, **outcome, "finished_at": _now(), "elapsed_seconds": elapsed}
