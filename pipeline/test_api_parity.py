"""Self-check: the library, the command line and the HTTP API produce identical output.

Run: python -m pipeline.test_api_parity
All three doors call pipeline.api, so any difference means one of them stopped doing so.
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from pipeline import extract, run
from pipeline.api import DEVICE_ENV, curate
from pipeline.cli import main as cli_main
from pipeline.server import Handler

SAMPLES = ("bank_of_baroda_kyc.pdf", "fiu_india_brochure.pdf", "rbi_kyc_fidcindia_aug2025.pdf")


def rows(text: str) -> list:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def main():
    raw_dir_before = extract.RAW_DIR
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pdfs = tmp / "pdfs"
        pdfs.mkdir()
        for name in SAMPLES:
            (pdfs / name).write_bytes((run.ROOT / "data" / "raw" / name).read_bytes())

        # --- library ------------------------------------------------------------------------
        lib = curate(pdfs, tmp / "lib", device="cpu")
        lib_rows = rows(lib.output_path.read_text(encoding="utf-8"))
        assert lib_rows and lib.summary["final_output_chunks"] == len(lib_rows)
        assert lib.device == "cpu" and DEVICE_ENV not in os.environ, "device env var must be restored"
        assert extract.RAW_DIR == raw_dir_before, "module paths must be restored after a run"
        assert lib.summary["stages"][0]["docs_in"] == len(SAMPLES), "ran on the given folder, not data/raw"

        # --- command line (a separate process) ----------------------------------------------
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        cli = subprocess.run(
            [sys.executable, "-m", "pipeline.cli", "run", str(pdfs), "-o", str(tmp / "cli")],
            capture_output=True, text=True, cwd=run.ROOT, env=env,
        )
        assert cli.returncode == 0, cli.stderr
        assert "chunks written:" in cli.stdout
        assert rows((tmp / "cli" / "curated.jsonl").read_text(encoding="utf-8")) == lib_rows

        # --- HTTP API (the real handler on a free port) --------------------------------------
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            body = json.dumps({"files": [
                {"name": n, "data": base64.b64encode((pdfs / n).read_bytes()).decode()} for n in SAMPLES
            ]}).encode()
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_address[1]}/api/run", body, {"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=900) as response:
                api = json.load(response)
        finally:
            server.shutdown()
        assert rows(api["curated_jsonl"]) == lib_rows
        assert api["summary"]["final_output_chunks"] == lib.summary["final_output_chunks"]
        assert api["summary"]["pii_entities_redacted"] == lib.summary["pii_entities_redacted"]

        # --- bad input fails cleanly ---------------------------------------------------------
        empty = tmp / "empty"
        empty.mkdir()
        for bad, error in ((tmp / "missing", FileNotFoundError), (empty, ValueError)):
            try:
                curate(bad, tmp / "x")
            except error:
                pass
            else:
                raise AssertionError(f"curate accepted {bad}")
        assert cli_main(["run", str(tmp / "missing"), "-o", str(tmp / "x")]) == 2

    print(f"ok: library, CLI and HTTP API agree on {len(lib_rows)} chunks; bad input rejected")


if __name__ == "__main__":
    main()
