"""`wasi:http` through `Preview2` (S0001, step C): a core module calls `wasi:http/outgoing-handler`, a hook answers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fusedwasi.p2.wasi_p2_http import HttpRequest, HttpResponse

import wasmhost
from wasmhost import Module
from wasmhost.wasi import Preview2

HTTP = Path(__file__).parent / "data" / "wasi2" / "http.wasm"


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


def test_the_hook_answers_the_request(session: str) -> None:
    hook = Hook()
    assert run(session, http=True, http_send=hook) == 0  # `http=True` alone: no `network=True` is needed
    assert len(hook.seen) == 1
    request = hook.seen[0]
    assert (request.method, request.scheme, request.authority, request.path) == ("GET", "http", "127.0.0.1:9", "/x?q=1")


def test_without_http_the_call_is_refused(session: str) -> None:
    hook = Hook()
    assert run(session, http_send=hook) == 1  # `handle` gave `HTTP-request-denied`
    assert run(session, network=True, http_send=hook) == 1  # the network is not wasi:http
    assert hook.seen == []


def test_http_check_decides(session: str) -> None:
    hook = Hook()
    assert run(session, http_check=lambda scheme, authority: authority == "127.0.0.1:9", http_send=hook) == 0
    assert run(session, http_check=lambda scheme, authority: False, http_send=hook) == 1
    assert len(hook.seen) == 1
