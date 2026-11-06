"""`examples/wasi2.py`: a WASI 0.2 program under `Preview2`, with and without the network."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

import wasmhost

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture
def example(session: str) -> ModuleType:
    if not wasmhost.get_backend().supports("imports"):
        pytest.skip(f"the {session} backend can't take imports")
    spec = importlib.util.spec_from_file_location("wasi2_example", EXAMPLES / "wasi2.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_hello(example: ModuleType, capfd: pytest.CaptureFixture[str]) -> None:
    assert example.main(["hello"]) == 0
    assert "hello from wasip2" in capfd.readouterr().out


def need_sockets(example: ModuleType) -> None:
    if sys.platform == "emscripten":
        pytest.skip("Python in Pyodide has no sockets")
    if not Path(example.SOCK).exists():
        pytest.skip("tests/data/wasi2/_sock.wasm is not there")


def test_sock_is_denied_by_default(example: ModuleType, capfd: pytest.CaptureFixture[str]) -> None:
    need_sockets(example)
    assert example.main(["sock"]) == 1
    captured = capfd.readouterr()  # the program's own text goes to stderr
    assert "connect: Permission denied" in captured.err and "the server saw: []" in captured.out


def test_sock_with_the_network(example: ModuleType, capfd: pytest.CaptureFixture[str]) -> None:
    need_sockets(example)
    assert example.main(["sock", "--network"]) == 0
    out = capfd.readouterr().out
    assert "reply: pong" in out and "the server saw: [b'ping']" in out
