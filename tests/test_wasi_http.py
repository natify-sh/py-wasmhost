"""`wasi:http` through `Preview2` (S0001, step C): a core module calls `wasi:http/outgoing-handler`, a hook answers."""

from __future__ import annotations

import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from fusedwasi.p2.wasi_p2_http import HttpRequest, HttpResponse

import wasmhost
from wasmhost import Module
from wasmhost.wasi import Preview2

HTTP = Path(__file__).parent / "data" / "wasi2" / "http.wasm"
PORT = 47124  # the authority that `http.wat` asks for
AUTHORITY = f"127.0.0.1:{PORT}"


@pytest.fixture(autouse=True)
def need_imports(session: str) -> None:
    if not wasmhost.get_backend().supports("imports"):
        pytest.skip(f"the {session} backend can't take imports")


class Hook:
    def __init__(self) -> None:
        self.seen: list[HttpRequest] = []

    def __call__(self, request: HttpRequest) -> HttpResponse:
        self.seen.append(request)
        return HttpResponse(200, [("Content-Type", b"text/plain")], b"canned")


def run(session: str, **options: Any) -> int:
    return Preview2(**options).run(Module(HTTP.read_bytes(), backend=session))


def run_text(session: str, **options: Any) -> tuple[int, bytes]:
    """The result of `run` and what the guest wrote to stdout (the status of the answer, three digits)."""
    out: list[bytes] = []
    return Preview2(stdout=out.append, **options).run(Module(HTTP.read_bytes(), backend=session)), b"".join(out)


def test_the_hook_answers_the_request(session: str) -> None:
    hook = Hook()
    # no `network=True` is needed; the guest read the status
    assert run_text(session, http=True, http_send=hook) == (0, b"200")
    assert len(hook.seen) == 1
    request = hook.seen[0]
    assert (request.method, request.scheme, request.authority, request.path) == ("GET", "http", AUTHORITY, "/x?q=1")


def test_without_http_the_call_is_refused(session: str) -> None:
    hook = Hook()
    assert run(session, http_send=hook) == 1  # `handle` gave `HTTP-request-denied`
    assert run(session, network=True, http_send=hook) == 1  # the network is not wasi:http
    assert hook.seen == []


def test_http_check_decides(session: str) -> None:
    hook = Hook()
    assert run(session, http_check=lambda scheme, authority: authority == AUTHORITY, http_send=hook) == 0
    assert run(session, http_check=lambda scheme, authority: False, http_send=hook) == 1
    assert len(hook.seen) == 1


# --- a real server: no hook, the h11 client of fusedwasi sends the request to 127.0.0.1


@pytest.fixture
def server() -> Iterator[list[tuple[str, str, dict[str, str]]]]:
    if sys.platform == "emscripten":  # Pyodide: Python has no sockets there
        pytest.skip("Python in Pyodide has no sockets")
    seen: list[tuple[str, str, dict[str, str]]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            seen.append((self.command, self.path, {k.lower(): v for k, v in self.headers.items()}))
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, format: str, *args: Any) -> None:
            pass

    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError as caught:
        pytest.skip(f"port {PORT} is busy: {caught}")
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield seen
    httpd.shutdown()
    httpd.server_close()
    thread.join(5)


def test_a_real_server_gets_the_request(session: str, server: list[tuple[str, str, dict[str, str]]]) -> None:
    assert run_text(session, http=True) == (0, b"200")  # the guest read the status of the server's answer
    assert len(server) == 1
    command, path, headers = server[0]
    assert (command, path, headers["host"]) == ("GET", "/x?q=1", AUTHORITY)


def test_a_real_server_sees_nothing_when_refused(session: str, server: list[tuple[str, str, dict[str, str]]]) -> None:
    assert run_text(session) == (1, b"")  # no `http=True`
    assert run_text(session, http=True, http_check=lambda scheme, authority: False) == (1, b"")
    assert server == []
