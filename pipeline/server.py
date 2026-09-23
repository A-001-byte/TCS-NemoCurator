"""Local API so the dashboard can push uploaded PDFs through the real pipeline.

  venv/Scripts/python -m pipeline.server        (listens on 127.0.0.1:8000)

POST /api/run  {"files": [{"name": "x.pdf", "data": "<base64>"}]}
  -> {"summary": <pipeline_summary.json>, "curated_jsonl": "<curated.jsonl text>", "log": "..."}

Each run gets its own temp data/ folder: every stage's module-level paths are
rebased there for the duration of the run, so the committed corpus is untouched.
"""
import base64
import binascii
import contextlib
import io
import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pipeline import clean, dedup, extract, output, pii, quality, run

HOST, PORT = "127.0.0.1", 8000
MAX_FILES = 10
MAX_TOTAL_BYTES = 30 * 1024 * 1024
DATA_DIR = run.ROOT / "data"
STAGE_DIRS = ("raw", "extracted", "cleaned", "deduped", "filtered", "redacted", "output")
MODULES = (extract, clean, dedup, quality, pii, output, run)

# ponytail: one run at a time, because runs patch module globals; a job queue if this ever serves more than one user.
RUN_LOCK = threading.Lock()


class BadRequest(Exception):
    pass


def _rebase(value, new_data_dir):
    if isinstance(value, Path) and value.is_relative_to(DATA_DIR):
        return new_data_dir / value.relative_to(DATA_DIR)
    if isinstance(value, dict) and value and all(isinstance(v, Path) for v in value.values()):
        return {k: _rebase(v, new_data_dir) for k, v in value.items()}
    return value


@contextlib.contextmanager
def _pipeline_rooted_at(tmp_root: Path):
    originals = {mod: dict(vars(mod)) for mod in MODULES}
    try:
        for mod in MODULES:
            for name, value in originals[mod].items():
                if name.isupper():
                    setattr(mod, name, _rebase(value, tmp_root / "data"))
        run.ROOT = tmp_root
        yield
    finally:
        for mod in MODULES:
            for name, value in originals[mod].items():
                if name.isupper():
                    setattr(mod, name, value)


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
    with RUN_LOCK, tempfile.TemporaryDirectory(prefix="kyc_run_") as tmp:
        tmp_root = Path(tmp)
        for sub in STAGE_DIRS:
            (tmp_root / "data" / sub).mkdir(parents=True)
        for name, data in files:
            (tmp_root / "data" / "raw" / name).write_bytes(data)

        log = io.StringIO()
        with _pipeline_rooted_at(tmp_root), contextlib.redirect_stdout(log):
            try:
                run.main()
            except SystemExit:
                return None, log.getvalue()
            summary = json.loads(run.SUMMARY_PATH.read_text(encoding="utf-8"))
            curated = output.OUT_PATH.read_text(encoding="utf-8")
        return {"summary": summary, "curated_jsonl": curated}, log.getvalue()


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
