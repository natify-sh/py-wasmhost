"""`examples/cpython/run2.py`: the official CPython built for wasm32-wasip2, run by `Preview2` (8 MB; seconds)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

import wasmhost

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "cpython"

PROGRAM = (
    "import sys, json, re, hashlib; print(sys.platform, json.dumps(re.findall(r'\\d+', 'a1b22')), "
    "hashlib.sha256(b'x').hexdigest()[:8], sum(range(10**6)))"
)
EXPECT = 'wasi ["1", "22"] 2d711642 499999500000'


@pytest.fixture
def example(session: str) -> ModuleType:
    if not wasmhost.get_backend().supports("imports"):
        pytest.skip(f"the {session} backend can't take imports")
    spec = importlib.util.spec_from_file_location("cpython_wasip2_example", EXAMPLE / "run2.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_program(example: ModuleType, capfd: pytest.CaptureFixture[str]) -> None:
    assert example.main(["-c", PROGRAM]) == 0
    assert capfd.readouterr().out.splitlines()[-1] == EXPECT


def test_exit_code_is_ok_or_err(example: ModuleType) -> None:
    # `wasi:cli/run#run` returns ok or err: CPython's 3 is err, which is 1 (the interface, not a defect)
    assert example.main(["-c", "import sys; sys.exit(0)"]) == 0
    assert example.main(["-c", "import sys; sys.exit(3)"]) == 1


LOOKUP = "import socket; print(socket.getaddrinfo('localhost', 80)[0][4][1])"


def test_the_network_is_open_by_default(example: ModuleType, capfd: pytest.CaptureFixture[str]) -> None:
    assert example.main(["-c", LOOKUP]) == 0  # the name lookup is allowed here, unlike in the library
    assert capfd.readouterr().out.splitlines()[-1] == "80"


def test_a_flag_closes_the_network(example: ModuleType, capfd: pytest.CaptureFixture[str]) -> None:
    assert example.main(["-S", "inherit-network=n,allow-ip-name-lookup=n", "-c", LOOKUP]) == 1
    assert "PermissionError" in capfd.readouterr().err


def test_env_reaches_the_program(example: ModuleType, capfd: pytest.CaptureFixture[str]) -> None:
    assert example.main(["--env", "WASMHOST_X=a=b", "-c", "import os; print(os.environ['WASMHOST_X'])"]) == 0
    assert capfd.readouterr().out.splitlines()[-1] == "a=b"
