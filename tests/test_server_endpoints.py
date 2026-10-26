"""Tests for the HTTP API: every route, every kind of bad request, busy and failure answers."""

import base64
import json
import socket
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from pipeline import __version__, api, server

PDF = b"%PDF-1.4 not a real document, only the header matters to the validator"


def b64(data: bytes = PDF) -> str:
    return base64.b64encode(data).decode()


def upload(*names, data=PDF):
    return {"files": [{"name": name, "data": b64(data)} for name in names]}


@pytest.fixture
def http(monkeypatch):
    """The real handler on a free port. `call(method, path, body)` returns (status, json, headers)."""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]

    def call(method, path, body=None, raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method, data=data)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.load(response), response.headers
        except urllib.error.HTTPError as error:
            return error.code, json.load(error), error.headers

    call.port = port
    yield call
    httpd.shutdown()
    httpd.server_close()


def raw_exchange(port: int, head: bytes, body: bytes = b"") -> tuple:
    """Send hand-written bytes and read the (status, json) answer: for requests a client library refuses to make."""
    with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
        sock.sendall(head + b"\r\n\r\n" + body)
        sock.shutdown(socket.SHUT_WR)
        chunks = []
        while chunk := sock.recv(65536):
            chunks.append(chunk)
    answer = b"".join(chunks)
    status = int(answer.split(b" ", 2)[1])
    return status, json.loads(answer.split(b"\r\n\r\n", 1)[1])


# --- routes and methods ---------------------------------------------------------------------------


def test_health_reports_the_version_and_the_responses_carry_safe_headers(http):
    status, body, headers = http("GET", "/api/health")
    assert (status, body) == (200, {"ok": True, "version": __version__})
    assert headers["Cache-Control"] == "no-store" and headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Server"] == "bfsi-curate", "the Python version must not be announced"
    assert http("GET", "/api/health?x=1")[0] == 200, "a query string is ignored"


@pytest.mark.parametrize(
    "method,path,allowed",
    [
        ("GET", "/api/run", "POST"),
        ("PUT", "/api/run", "POST"),
        ("DELETE", "/api/run", "POST"),
        ("POST", "/api/health", "GET"),
        ("PATCH", "/api/health", "GET"),
        ("GET", "/api/refresh", "POST"),
        ("POST", "/api/refresh/status", "GET"),
    ],
)
def test_a_known_path_with_the_wrong_method_is_405_with_an_allow_header(http, method, path, allowed):
    status, body, headers = http(method, path, raw=b"" if method in ("POST", "PUT", "PATCH") else None)
    assert status == 405 and allowed in body["error"] and headers["Allow"] == allowed


@pytest.mark.parametrize(
    "method,path", [("GET", "/"), ("GET", "/api"), ("POST", "/api/nothing"), ("GET", "/api/run/extra")]
)
def test_an_unknown_path_is_404_json(http, method, path):
    status, body, _ = http(method, path, raw=b"" if method == "POST" else None)
    assert status == 404 and body == {"error": "Not found."}


# --- /api/run: bad requests ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "body,message",
    [
        (None, "Send at least one PDF."),  # no body at all
        ([], "Send at least one PDF."),
        ({"files": []}, "Send at least one PDF."),
        ({"files": "x.pdf"}, "Send at least one PDF."),
        ({"files": ["x.pdf"]}, "Each file must be"),
        ({"files": [{"name": "x.pdf"}]}, "Each file must be"),
        ({"files": [{"name": 5, "data": "AA=="}]}, "Each file must be"),
        ({"files": [{"name": "x.pdf", "data": 5}]}, "Each file must be"),
        ({"files": [{"name": "notes.txt", "data": "AA=="}]}, "not a .pdf"),
        ({"files": [{"name": "", "data": "AA=="}]}, "invalid name"),
        ({"files": [{"name": "..", "data": "AA=="}]}, "invalid name"),
        ({"files": [{"name": "a\x00b.pdf", "data": "AA=="}]}, "invalid name"),
        ({"files": [{"name": "x.pdf", "data": "!!not base64!!"}]}, "could not be decoded"),
        ({"files": [{"name": "x.pdf", "data": b64(b"hello")}]}, "not a valid PDF"),
        (upload("a.pdf", "A.PDF"), "Two files are named"),
        (upload(*[f"{i}.pdf" for i in range(server.MAX_FILES + 1)]), "At most"),
    ],
)
def test_a_bad_upload_is_400_with_a_reason_and_never_starts_the_pipeline(http, monkeypatch, body, message):
    monkeypatch.setattr(server, "run_on_upload", lambda files: pytest.fail("the pipeline must not start"))
    status, answer, _ = http("POST", "/api/run", body)
    assert status == 400 and message in answer["error"], answer


def test_json_null_is_answered_not_dropped(http):
    """A body of `null` parses to None: it must still get a 400, not hang the client."""
    status, answer, _ = http("POST", "/api/run", raw=b"null")
    assert status == 400 and "at least one PDF" in answer["error"]


@pytest.mark.parametrize("raw", [b"{not json", b"\xff\xfe\x00 not utf-8", b"<xml/>"])
def test_a_body_that_is_not_json_is_400(http, raw):
    status, answer, _ = http("POST", "/api/run", raw=raw)
    assert status == 400 and "not JSON" in answer["error"]


def test_the_total_size_limit_is_enforced(http, monkeypatch):
    monkeypatch.setattr(server, "MAX_TOTAL_BYTES", 100)
    status, answer, _ = http("POST", "/api/run", upload("a.pdf", "b.pdf", data=PDF + b"x" * 40))
    assert status == 400 and "larger than" in answer["error"]


def test_a_folder_part_in_a_file_name_is_stripped_not_trusted():
    decoded = server._decode_files(upload("..\\..\\evil.pdf", "/etc/other.pdf", "sub/dir/ok.PDF"))
    assert [name for name, _ in decoded] == ["evil.pdf", "other.pdf", "ok.PDF"]


# --- /api/run: malformed requests only raw bytes can make ---------------------------------------------


@pytest.mark.parametrize("length", [b"abc", b"-5", b"1.5", b""])
def test_a_bad_content_length_is_400(http, length):
    status, answer = raw_exchange(http.port, b"POST /api/run HTTP/1.1\r\nHost: x\r\nContent-Length: " + length)
    assert status == 400 and "Content-Length" in answer["error"]


def test_a_huge_declared_body_is_413_before_anything_is_read(http):
    status, answer = raw_exchange(http.port, b"POST /api/run HTTP/1.1\r\nHost: x\r\nContent-Length: 999999999")
    assert status == 413 and "too large" in answer["error"]


def test_a_body_shorter_than_declared_is_400(http):
    status, answer = raw_exchange(
        http.port, b"POST /api/run HTTP/1.1\r\nHost: x\r\nContent-Length: 500", b'{"files": ['
    )
    assert status == 400 and "cut short" in answer["error"]


# --- /api/run: what the pipeline does ---------------------------------------------------------------


def test_a_successful_run_returns_the_summary_the_curated_text_and_the_log(http, monkeypatch):
    seen = {}

    def fake(files):
        seen["files"] = files
        return {"summary": {"final_output_chunks": 3}, "curated_jsonl": '{"text": "x"}\n'}, "stage log"

    monkeypatch.setattr(server, "run_on_upload", fake)
    status, body, _ = http("POST", "/api/run", upload("a.pdf"))
    assert status == 200 and body == {
        "summary": {"final_output_chunks": 3},
        "curated_jsonl": '{"text": "x"}\n',
        "log": "stage log",
    }
    assert seen["files"] == [("a.pdf", PDF)]


def test_a_pipeline_that_stops_is_422_with_the_reason_in_plain_words(http, monkeypatch):
    log = "...\nPipeline stopped: stage 'extract' failed (exit 1)"
    monkeypatch.setattr(server, "run_on_upload", lambda files: (None, log))
    status, body, _ = http("POST", "/api/run", upload("a.pdf"))
    assert (
        status == 422
        and "extract stage" in body["error"]
        and "no PDF yielded any text" in body["error"]
        and body["log"] == log
    )


def test_a_crash_inside_the_pipeline_is_500_and_the_server_keeps_serving(http, monkeypatch):
    def boom(files):
        raise ValueError("disk on fire")

    monkeypatch.setattr(server, "run_on_upload", boom)
    status, body, _ = http("POST", "/api/run", upload("a.pdf"))
    assert status == 500 and "disk on fire" in body["error"]
    assert http("GET", "/api/health")[0] == 200


def test_an_unexpected_error_in_a_route_is_a_generic_500_that_leaks_nothing(http, monkeypatch):
    class Broken:
        def status(self):
            raise RuntimeError("secret internal detail")

    monkeypatch.setattr(server, "REFRESH_JOB", Broken())
    status, body, _ = http("GET", "/api/refresh/status")
    assert status == 500 and body == {"error": "Internal server error."}
    assert http("GET", "/api/health")[0] == 200


def test_a_second_run_while_one_is_in_progress_is_409_at_once_not_a_wait(http):
    """With the real lock held (as during a refresh), an upload is turned away immediately."""
    assert api.RUN_LOCK.acquire(blocking=False)
    try:
        status, body, _ = http("POST", "/api/run", upload("a.pdf"))
    finally:
        api.RUN_LOCK.release()
    assert status == 409 and "in progress" in body["error"]
