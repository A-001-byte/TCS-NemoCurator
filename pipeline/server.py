"""Local API so the dashboard can push uploaded PDFs through the real pipeline.

  venv/Scripts/python -m pipeline.server        (listens on 127.0.0.1:8000)

POST /api/run  {"files": [{"name": "x.pdf", "data": "<base64>"}]}
  -> {"summary": <pipeline_summary.json>, "curated_jsonl": "<curated.jsonl text>", "log": "..."}

The run itself lives in pipeline.api (the same code the library and the CLI use): each run gets
its own temp data/ folder, so the committed corpus is untouched.
"""
import base64
import binascii
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pipeline.api import run_isolated

HOST, PORT = "127.0.0.1", 8000
MAX_FILES = 10
MAX_TOTAL_BYTES = 30 * 1024 * 1024


class BadRequest(Exception):
    pass


def _decode_files(payload):
    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(files, list) or not files:
        raise BadRequest("Send at least one PDF.")
    if len(files) > MAX_FILES:
        raise BadRequest(f"At most {MAX_FILES} files per run.")

    decoded, total = [], 0
    for item in files:
        name = Path(str(item.get("name", ""))).name  # strip any directory parts
        if not name.lower().endswith(".pdf"):
            raise BadRequest(f"{name or 'A file'} is not a .pdf file.")
        try:
            data = base64.b64decode(item.get("data", ""), validate=True)
        except (binascii.Error, ValueError):
            raise BadRequest(f"{name} could not be decoded.") from None
        if not data.startswith(b"%PDF"):
            raise BadRequest(f"{name} is not a valid PDF.")
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise BadRequest(f"Upload is larger than {MAX_TOTAL_BYTES // (1024 * 1024)} MB.")
        decoded.append((name, data))
    return decoded


def run_on_upload(files):
    """(result, log) for a list of (name, pdf_bytes); result is None if the pipeline stopped."""
    return run_isolated(files)


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body):
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/api/health":
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "Not found"})

    def do_POST(self):
        if self.path != "/api/run":
            return self._send(404, {"error": "Not found"})
        length = int(self.headers.get("Content-Length") or 0)
        # base64 inflates by 4/3; allow for the JSON wrapper too
        if length > MAX_TOTAL_BYTES * 4 // 3 + 64 * 1024:
            return self._send(413, {"error": "Upload is too large."})
        try:
            files = _decode_files(json.loads(self.rfile.read(length) or b"{}"))
        except json.JSONDecodeError:
            return self._send(400, {"error": "Request body is not JSON."})
        except BadRequest as exc:
            return self._send(400, {"error": str(exc)})

        try:
            result, log = run_on_upload(files)
        except Exception as exc:  # report pipeline crashes to the UI instead of dropping the connection
            self.log_error("pipeline crashed: %r", exc)
            return self._send(500, {"error": f"Pipeline crashed: {exc}"})
        if result is None:
            return self._send(422, {"error": "The pipeline stopped before finishing.", "log": log})
        self._send(200, {**result, "log": log})


if __name__ == "__main__":
    print(f"Pipeline API on http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
