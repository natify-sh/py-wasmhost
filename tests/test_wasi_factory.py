"""`wasmhost.wasi.for_module` (S0005): the host that fits the module, from its imports."""

from __future__ import annotations

from pathlib import Path

import pytest
import wasm_builder as wb

import wasmhost
from wasmhost import Module
from wasmhost.wasi import Preview1, Preview2, for_module

ONE = (Path(__file__).parent / "data" / "wasi2" / "one.wasm").read_bytes()


@pytest.fixture(autouse=True)
def need_imports(session: str) -> None:
    if not wasmhost.get_backend().supports("imports"):
        pytest.skip(f"the {session} backend can't take imports")


def test_a_module_of_wasi_01_gets_preview1_and_runs() -> None:
    out: list[bytes] = []
    wasm = wb.wasi_hello()
    with for_module(wasm, args=["x", "y"], stdout=out.append) as wasi:
        assert isinstance(wasi, Preview1)
        assert wasi.run(Module(wasm)) == 2
    assert b"".join(out) == b"hello, wasi\n"


def test_a_module_of_wasi_02_gets_preview2_and_runs() -> None:
    out: list[bytes] = []
    with for_module(ONE, env={"A": "1"}, stdout=out.append) as wasi:
        assert isinstance(wasi, Preview2)
        assert wasi.run(Module(ONE)) == 0
    assert b"".join(out) == b"hello from wasip2\n"


def test_imports_takes_the_module_on_both() -> None:
    for wasm in (wb.wasi_hello(), ONE):
        with for_module(wasm) as wasi:
            assert wasi.imports(Module(wasm))


def test_a_module_without_wasi_gets_preview1() -> None:
    with for_module(wb.arith()) as wasi:
        assert isinstance(wasi, Preview1)


def test_a_component_is_refused() -> None:
    with pytest.raises(ValueError, match="component.*unbundle.*meld fuse"):
        for_module(b"\0asm\x0d\x00\x01\x00")


def test_wasi_03_is_refused() -> None:
    with pytest.raises(ValueError, match="WASI 0.3 is not supported"):
        for_module(ONE.replace(b"wasi:cli/exit@0.2.6", b"wasi:cli/exit@0.3.0"))


def test_bytes_that_are_no_module_are_refused() -> None:
    with pytest.raises(ValueError, match="not a WebAssembly core module"):
        for_module(b"hello")


@pytest.mark.parametrize("option", ["network", "http", "import_map", "socket_addr_check"])
def test_an_option_of_wasi_02_for_a_module_of_01_names_the_option(option: str) -> None:
    with pytest.raises(ValueError, match=f"`{option}`"):
        for_module(wb.wasi_hello(), **{option: True})
    with for_module(ONE, **{option: None if option == "import_map" else False}) as wasi:  # accepted by 0.2
        assert isinstance(wasi, Preview2)
