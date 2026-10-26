"""Tests for the background refresh: the job's states and the /api/refresh routes."""

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from pipeline import server
from pipeline.refresh_job import FAILED, IDLE, RUNNING, SUCCEEDED, RefreshJob

SUMMARY = {"final_output_chunks": 3325, "pii_entities_redacted": 68}


def wait_for(predicate, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("timed out waiting for the job")


def gated_job():
    """A job whose fake pipeline waits for `release` and returns SUMMARY, or raises if told to."""
    release = threading.Event()
    behaviour = {"error": None}

    def run():
        assert release.wait(5), "the test never released the fake pipeline"
        if behaviour["error"]:
            raise behaviour["error"]
        return SUMMARY

    return RefreshJob(run), release, behaviour


def test_a_job_goes_from_idle_to_running_to_succeeded_and_never_runs_twice():
    job, release, _ = gated_job()
    assert job.status() == {"state": IDLE}

    assert job.start() is True
    running = job.status()
    assert running["state"] == RUNNING and "started_at" in running and "elapsed_seconds" in running
    assert job.start() is False, "a second start while running must be refused"

    release.set()
    wait_for(lambda: job.status()["state"] == SUCCEEDED)
    done = job.status()
    assert done["chunks"] == 3325 and done["pii_entities"] == 68
    assert done["finished_at"] and done["elapsed_seconds"] >= 0
    assert job.start() is True, "a finished job can be started again"
    release.set()


def test_a_failure_is_reported_and_does_not_block_the_next_run():
    job, release, behaviour = gated_job()
    behaviour["error"] = RuntimeError("boom")
    release.set()
    assert job.start()
    wait_for(lambda: job.status()["state"] == FAILED)
    assert job.status()["error"] == "RuntimeError: boom"

    behaviour["error"] = None
    assert job.start(), "after a failure the job can be started again"
    wait_for(lambda: job.status()["state"] == SUCCEEDED)
    assert "error" not in job.status()


@pytest.fixture
def api(monkeypatch):
    """The real HTTP handler on a free port, with a fake pipeline behind /api/refresh."""
    job, release, _ = gated_job()
    monkeypatch.setattr(server, "REFRESH_JOB", job)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]

    def call(method, path):
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}", method=method, data=b"" if method == "POST" else None
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    yield call, release
    release.set()
    httpd.shutdown()
    httpd.server_close()


def test_the_refresh_routes_start_a_job_report_busy_and_report_the_result(api):
    call, release = api
    assert call("GET", "/api/refresh/status") == (200, {"state": "idle"})

    status, body = call("POST", "/api/refresh")
    assert status == 202 and body["state"] == "running"

    status, body = call("POST", "/api/refresh")
    assert status == 409 and body["state"] == "running" and "already running" in body["error"]
    assert call("GET", "/api/refresh/status")[1]["state"] == "running"

    release.set()
    wait_for(lambda: call("GET", "/api/refresh/status")[1]["state"] == "succeeded")
    status, body = call("GET", "/api/refresh/status")
    assert status == 200 and body["chunks"] == 3325


def test_a_get_on_the_refresh_route_is_refused_and_never_starts_a_run(api):
    call, _ = api
    status, body = call("GET", "/api/refresh")
    assert status == 405 and "POST" in body["error"]
    assert call("GET", "/api/refresh/status") == (200, {"state": "idle"}), "the GET must not have started a job"
    assert call("POST", "/api/nothing")[0] == 404
    status, body = call("GET", "/api/health")
    assert status == 200 and body["ok"] is True


def test_refresh_job_passes_selected_options_to_the_run():
    seen = {}

    def run(**options):
        seen.update(options)
        return SUMMARY

    job = RefreshJob(run)
    assert job.start({"device": "cuda", "quality_signal": "model"})
    wait_for(lambda: job.status()["state"] == SUCCEEDED)
    assert seen == {"device": "cuda", "quality_signal": "model"}
    assert job.status()["device"] == "cuda"


def test_refresh_route_passes_settings_and_rejects_bad_values(monkeypatch):
    seen = {}

    class SpyJob:
        def start(self, options):
            seen.update(options)
            return True

        def status(self):
            return {"state": "running"}

    monkeypatch.setattr(server, "REFRESH_JOB", SpyJob())
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{httpd.server_address[1]}/api/refresh"

        def post(payload):
            request = urllib.request.Request(
                url,
                method="POST",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    return response.status, json.load(response)
            except urllib.error.HTTPError as error:
                return error.code, json.load(error)

        assert post({"device": "cuda", "quality_signal": "model"})[0] == 202
        assert seen == {"device": "cuda", "quality_signal": "model"}
        status, body = post({"device": "not-a-gpu"})
        assert status == 400 and "device must be one of" in body["error"]
    finally:
        httpd.shutdown()
        httpd.server_close()
