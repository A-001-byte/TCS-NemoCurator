"""Local API so the dashboard can push uploaded PDFs through the real pipeline.

    python -m pipeline.server [--host 127.0.0.1] [--port 8000]
    bfsi-curate serve [--host ...] [--port ...]          (the same thing)

The address can also come from CURATOR_HOST and CURATOR_PORT; a flag wins over the environment.

Routes (JSON in, JSON out). Every failure is {"error": "<what went wrong>"} with a fitting status:

  GET  /api/health          -> {"ok": true, "version": "0.1.0"}
  POST /api/run  {"files": [{"name": "x.pdf", "data": "<base64>"}]}
      -> {"summary": <pipeline_summary.json>, "curated_jsonl": "<curated.jsonl text>", "log": "..."}
      400 bad request, 409 another run is in progress, 413 too large, 422 the pipeline stopped
  POST /api/refresh         -> 202 {"state": "running", ...}, or 409 if a refresh is already running
  GET  /api/refresh/status  -> {"state": "idle" | "running" | "succeeded" | "failed", ...}
  a known path with the wrong method -> 405 with an Allow header; an unknown path -> 404

The run itself lives in pipeline.api (the same code the library and the CLI use): each run gets its
own temp data/ folder, so the committed corpus is untouched. A refresh re-runs the whole corpus
(minutes) in a background thread and republishes the dashboard snapshots. There is no
authentication: keep the default loopback address unless the network is trusted.
"""

import argparse
import base64
import binascii
import json
import logging
import os
import re
import signal
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from pipeline import __version__
from pipeline.api import PipelineBusy, run_isolated, stop_reason
from pipeline.device import describe, pick
from pipeline.refresh_job import RefreshJob
from pipeline.refresh_snapshots import refresh

log = logging.getLogger(__name__)

DEFAULT_HOST, DEFAULT_PORT = "127.0.0.1", 8000
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
MAX_FILES = 10
MAX_TOTAL_BYTES = 30 * 1024 * 1024
MAX_NAME_CHARS = 150
# base64 inflates by 4/3; allow for the JSON wrapper too
MAX_BODY_BYTES = MAX_TOTAL_BYTES * 4 // 3 + 64 * 1024

REFRESH_JOB = RefreshJob(refresh)


class BadRequest(Exception):
    pass


class HttpError(Exception):
    """A request that must be answered with this status and message."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _clean_name(raw) -> str:
    """The file name without any folder part (either kind of slash), or BadRequest."""
    name = re.split(r"[\\/]", raw)[-1].strip()
    if not name or name in (".", "..") or len(name) > MAX_NAME_CHARS or any(ord(c) < 32 for c in name):
        raise BadRequest("A file has an invalid name.")
    if not name.lower().endswith(".pdf"):
        raise BadRequest(f"{name} is not a .pdf file.")
    return name


def _decode_files(payload) -> list:
    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(files, list) or not files:
        raise BadRequest("Send at least one PDF.")
    if len(files) > MAX_FILES:
        raise BadRequest(f"At most {MAX_FILES} files per run.")

    decoded, seen, total = [], set(), 0
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not isinstance(item.get("data"), str):
            raise BadRequest('Each file must be {"name": "x.pdf", "data": "<base64>"}.')
        name = _clean_name(item["name"])
        if name.lower() in seen:
            raise BadRequest(f"Two files are named {name}.")
        seen.add(name.lower())
        try:
            data = base64.b64decode(item["data"], validate=True)
        except (binascii.Error, ValueError):
            raise BadRequest(f"{name} could not be decoded.") from None
        if not data.startswith(b"%PDF"):
            raise BadRequest(f"{name} is not a valid PDF.")
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise BadRequest(f"Upload is larger than {MAX_TOTAL_BYTES // (1024 * 1024)} MB.")
        decoded.append((name, data))
    return decoded


def run_on_upload(files: list, *, device: str = "auto", quality_signal: str = "off") -> tuple:
    """(result, log) for uploaded PDFs with a per-run device and quality choice."""
    return run_isolated(
        files,
        wait=False,
        pii_engine="regex",
        quality_signal=quality_signal,
        device=device,
    )


def _run_options(payload) -> dict:
    """Validate optional per-run choices; omitted fields keep endpoint defaults."""
    if not isinstance(payload, dict):
        raise BadRequest("Run settings must be a JSON object.")
    options = {}
    for field, choices in (("device", ("auto", "cpu", "cuda")), ("quality_signal", ("off", "model"))):
        if field in payload:
            if payload[field] not in choices:
                raise BadRequest(f"{field} must be one of: {', '.join(choices)}.")
            options[field] = payload[field]
    return options


class Handler(BaseHTTPRequestHandler):
    server_version = "bfsi-curate"
    sys_version = ""  # do not announce the Python version

    def version_string(self):
        return self.server_version

    def log_message(self, format, *args):  # noqa: A002 - signature set by BaseHTTPRequestHandler
        log.info("%s %s", self.address_string(), format % args)

    # --- responses ---------------------------------------------------------------------------
    def _send(self, status, body, headers=None):
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def _error(self, status, message, headers=None, **extra):
        self._send(status, {"error": message, **extra}, headers)

    # --- routing -----------------------------------------------------------------------------
    def _handle(self, method):
        path = urlsplit(self.path).path
        routes = {
            ("GET", "/api/health"): self._health,
            ("GET", "/api/capabilities"): self._capabilities,
            ("GET", "/api/refresh/status"): self._refresh_status,
            ("POST", "/api/refresh"): self._refresh_start,
            ("POST", "/api/run"): self._run,
        }
        handler = routes.get((method, path))
        if handler is None:
            allowed = sorted(m for m, p in routes if p == path)
            if allowed:
                return self._error(405, f"Use {' or '.join(allowed)} for this route.", {"Allow": ", ".join(allowed)})
            return self._error(404, "Not found.")
        try:
            handler()
        except HttpError as exc:
            self._error(exc.status, str(exc))
        except Exception:  # never drop the connection: report it and keep serving
            log.exception("unhandled error in %s %s", method, path)
            self._error(500, "Internal server error.")

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def do_PATCH(self):
        self._handle("PATCH")

    def do_DELETE(self):
        self._handle("DELETE")

    # --- routes ------------------------------------------------------------------------------
    def _health(self):
        self._send(200, {"ok": True, "version": __version__})

    def _capabilities(self):
        gpu = pick("cuda")
        self._send(
            200,
            {"cuda_available": gpu.startswith("cuda"), "gpu_name": describe(gpu) if gpu.startswith("cuda") else None},
        )

    def _refresh_status(self):
        self._send(200, REFRESH_JOB.status())

    def _refresh_start(self):
        try:
            options = _run_options(self._read_json())
        except BadRequest as exc:
            return self._error(400, str(exc))
        if REFRESH_JOB.start(options):
            return self._send(202, REFRESH_JOB.status())
        self._error(409, "A refresh is already running.", **REFRESH_JOB.status())

    def _read_json(self):
        """The request body as parsed JSON; raises HttpError for a body that cannot be read."""
        header = self.headers.get("Content-Length")
        if header is None:
            return {}
        if not header.isdigit():
            raise HttpError(400, "Invalid Content-Length.")
        length = int(header)
        if length > MAX_BODY_BYTES:
            raise HttpError(413, "Upload is too large.")
        raw = self.rfile.read(length)
        if len(raw) < length:
            raise HttpError(400, "The request body was cut short.")
        try:
            return json.loads(raw or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HttpError(400, "Request body is not JSON.") from None

    def _run(self):
        try:
            payload = self._read_json()
            files = _decode_files(payload)
            options = _run_options(payload)
        except BadRequest as exc:
            return self._error(400, str(exc))
        try:
            result, pipeline_log = run_on_upload(files, **options)
        except PipelineBusy as exc:
            return self._error(409, str(exc))
        except RuntimeError as exc:
            return self._error(422, str(exc))
        except Exception as exc:  # report pipeline crashes to the UI instead of dropping the connection
            log.exception("pipeline crashed")
            return self._error(500, f"Pipeline crashed: {exc}")
        if result is None:
            return self._error(422, stop_reason(pipeline_log), log=pipeline_log)
        self._send(200, {**result, "log": pipeline_log})


def make_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def _address(argv):
    """(host, port) from flags, then CURATOR_HOST / CURATOR_PORT, then the defaults."""
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.server", description="Local pipeline API for the dashboard."
    )
    parser.add_argument("--host", default=os.environ.get("CURATOR_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args(argv)
    port = args.port
    if port is None:
        try:
            port = int(os.environ.get("CURATOR_PORT", DEFAULT_PORT))
        except ValueError:
            parser.error("CURATOR_PORT must be a number")
    if not 1 <= port <= 65535:
        parser.error("--port must be between 1 and 65535")
    return args.host, port


def main(argv=None) -> int:
    host, port = _address(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if host not in LOOPBACK_HOSTS:
        log.warning(
            "Listening on %s: this API has no authentication; use %s unless the network is trusted.", host, DEFAULT_HOST
        )
    try:
        httpd = make_server(host, port)
    except OSError as exc:
        log.error("Cannot listen on %s:%s (%s)", host, port, exc)
        return 1

    def stop(signum, frame):  # SIGTERM (a service manager, `docker stop`) shuts down like Ctrl+C
        raise KeyboardInterrupt

    if threading.current_thread() is threading.main_thread():  # signals can only be set up there
        signal.signal(signal.SIGTERM, stop)
    log.info("Pipeline API on http://%s:%s", host, port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
