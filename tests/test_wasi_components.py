"""S0004: WASI 0.2 of a module that `meld` fused from several components, routed by the import map. `two_multi.wasm`
is two components (A calls B's `add`) in two memories; `two_shared.wasm` the same two in one memory (the shared
fusion, run as one component). The JavaScriptCore engines refuse a module with several memories (S0003)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import wasm_builder as wb

import wasmhost
from wasmhost import LinkError, Module
from wasmhost.wasi import Preview2

DATA = Path(__file__).parent / "data" / "wasi2"
RUN = "demo:m/app@0.1.0#run"
TEXT = b"A-text-ALPHA 2 prog x\nB-text-BRAVO 2 prog x\nA-after-add 2 prog x\n"
MAP_PATH = DATA / "two_multi.map.json"
CX_MAP = Path(__file__).parent.parent / "docs" / "experiments" / "s0001_wasi2" / "cx.import-map.v2.json"


@pytest.fixture(autouse=True)
def need_imports(session: str) -> None:
    if not wasmhost.get_backend().supports("imports"):
        pytest.skip(f"the {session} backend can't take imports")


def load(session: str, name: str) -> Module:
    try:
        return Module((DATA / f"{name}.wasm").read_bytes(), backend=session)
    except wasmhost.CompileError as exc:
        pytest.skip(f"the {session} engine refuses a module with several memories: {exc}")


def the_map() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(MAP_PATH.read_text())
    return loaded


def run_text(wasi_module: Module, **options: Any) -> tuple[int, bytes]:
    out: list[bytes] = []
    wasi = Preview2(args=["prog", "x"], stdout=out.append, **options)
    try:
        instance = wasi.instantiate(wasi_module)
        entry: Any = instance.exports[RUN]
        return int(entry()), b"".join(out)
    finally:
        wasi.close()


def test_the_routed_module_writes_each_text_in_order_from_its_own_memory(session: str) -> None:
    module = load(session, "two_multi")
    assert run_text(module, import_map=MAP_PATH) == (42, TEXT)  # a path
    assert run_text(module, import_map=the_map()) == (42, TEXT)  # the loaded JSON


def test_every_import_routed_to_component_zero_is_corrupt(session: str) -> None:
    flat = the_map()
    for entry in flat["imports"]:
        if entry["memory"]:
            entry["memory"] = {"export": "memory", "index": 0}
        if entry["realloc"]:
            entry["realloc"] = {"export": "cabi_realloc", "func": 0}
    _, text = run_text(load(session, "two_multi"), import_map=flat)
    assert text != TEXT
    assert b"A-text-ALPHA" not in text  # A's first line was read from the wrong memory


def test_several_components_without_a_map_is_refused(session: str) -> None:
    with pytest.raises(ValueError, match="import_map=.*meld fuse --emit-import-map.*fuse one component"):
        Preview2().imports(load(session, "two_multi"))


def test_the_shared_fusion_is_one_component_and_needs_no_map(session: str) -> None:
    module = load(session, "two_shared")
    assert run_text(module) == (42, TEXT)
    assert run_text(module, import_map=DATA / "two_shared.map.json") == (
        42,
        TEXT,
    )  # a map of a one-realloc module is ignored


def test_a_map_of_another_version_is_refused() -> None:
    bad = the_map()
    bad["version"] = 3
    with pytest.raises(ValueError, match="version 3.*only version 2"):
        Preview2(import_map=bad)


def test_a_valid_map_is_read() -> None:
    Preview2(import_map=CX_MAP).close()
    Preview2(import_map=the_map()).close()


def test_the_map_is_not_given_with_a_state() -> None:
    with Preview2() as first, pytest.raises(TypeError, match="no other option"):
        Preview2(state=first.state, import_map=the_map())


def test_an_untraced_entry_is_named(session: str) -> None:
    bad = the_map()
    bad["imports"][1]["realloc"] = {"unknown": "no canon lower"}
    with pytest.raises(LinkError, match=r"get-arguments.*realloc.*no canon lower"):
        Preview2(import_map=bad).imports(load(session, "two_multi"))


def test_an_import_missing_from_the_map_is_named(session: str) -> None:
    bad = the_map()
    del bad["imports"][2]
    with pytest.raises(LinkError, match=r"no entry for wasi:io/streams@0.2.12 \[method\]output-stream"):
        Preview2(import_map=bad).imports(load(session, "two_multi"))


def test_a_duplicate_import_is_refused(session: str) -> None:
    get_stdout = wb.name("wasi:cli/stdout@0.2.12") + wb.name("get-stdout") + b"\x00\x00"
    exports = [("cabi_realloc", 0, 2), ("cabi_realloc$1", 0, 3)]
    types = [wb.functype([], [wb.I32]), wb.functype([wb.I32] * 4, [wb.I32])]
    funcs: list[wb.Func] = [(1, b"\x41\x00"), (1, b"\x41\x00")]
    module = Module(wb.module(types, funcs, exports, imports=[get_stdout, get_stdout]), backend=session)
    with pytest.raises(LinkError, match="imports wasi:cli/stdout@0.2.12 get-stdout twice"):
        Preview2(import_map=the_map()).imports(module)
