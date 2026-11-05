"""S0003: a module with several memories. Each memory the module exports or imports is a `Memory` by its name; a
memory that is neither is reachable through the module's own functions only. The JavaScriptCore engines refuse such
a module (a CompileError), so these tests are skipped there with the engine's message."""

from __future__ import annotations

import pytest
import wasm_builder as wb

import wasmhost

PAGE = 65536


def _mem(exports: object, name: str) -> wasmhost.Memory:
    found = exports[name]  # type: ignore[index]
    assert isinstance(found, wasmhost.Memory)
    return found


@pytest.fixture
def three(session: str) -> wasmhost.Module:
    try:
        return wasmhost.Module(wb.three_memories())
    except wasmhost.CompileError as exc:
        pytest.skip(f"the {wasmhost.get_backend().name} engine refuses a module with several memories: {exc}")


@pytest.fixture
def two_imported(session: str) -> wasmhost.Module:
    backend = wasmhost.get_backend()
    if not backend.supports("import.memory"):
        pytest.skip(f"the {backend.name} backend has no import.memory")
    try:
        return wasmhost.Module(wb.imports_two_memories())
    except wasmhost.CompileError as exc:
        pytest.skip(f"the {backend.name} engine refuses a module with several memories: {exc}")


def test_the_exported_memories_are_separate(three: wasmhost.Module) -> None:
    ex = wasmhost.Instance(three).exports
    a, b = _mem(ex, "a"), _mem(ex, "b")
    assert [(e.name, e.kind) for e in wasmhost.Module.exports(three) if e.kind == "memory"] == [
        ("a", "memory"),
        ("b", "memory"),
    ]
    assert (len(a), len(b)) == (PAGE, 2 * PAGE)
    a.write(100, b"first")
    b.write(100, b"second")
    assert (a.read(100, 5), b.read(100, 6)) == (b"first", b"second")
    assert (a.type(), b.type()) == (wasmhost.MemoryType(1, 4, False), wasmhost.MemoryType(2, None, False))
    assert b.read(0, 4) == b"\0\0\0\0"  # the data segment of memory 0 did not land in memory 1


def test_data_segments_land_in_their_memory(three: wasmhost.Module) -> None:
    ex = wasmhost.Instance(three).exports
    assert (
        _mem(ex, "a").read(0, 2) == b"AA"
        and _mem(ex, "a").read(4, 2) == b"\0\0"
        and _mem(ex, "a").read(8, 2) == b"\0\0"
    )
    assert (
        _mem(ex, "b").read(4, 2) == b"BB"
        and _mem(ex, "b").read(0, 2) == b"\0\0"
        and _mem(ex, "b").read(8, 2) == b"\0\0"
    )
    assert [ex.load2(8 + i) for i in range(3)] == [ord("C"), ord("C"), 0]  # memory 2: only the module reaches it
    assert ex.load2(0) == 0 and ex.load2(4) == 0


def test_grow_inside_the_module_touches_one_memory(three: wasmhost.Module) -> None:
    ex = wasmhost.Instance(three).exports
    assert (ex.size0(), ex.size1(), ex.size2()) == (1, 2, 1)
    assert ex.grow1(3) == 2  # the old size of memory 1 only
    assert (ex.size0(), ex.size1(), ex.size2()) == (1, 5, 1)
    assert (len(_mem(ex, "a")), len(_mem(ex, "b"))) == (PAGE, 5 * PAGE)
    assert ex.grow2(2) == 1
    assert (ex.size0(), ex.size1(), ex.size2()) == (1, 5, 3)
    assert ex.grow0(4) == -1  # memory 0 has a maximum of 4 pages, 1 + 4 is over it
    assert (ex.grow0(3), ex.size0(), len(_mem(ex, "a"))) == (1, 4, 4 * PAGE)


def test_grow_from_python_touches_one_memory(three: wasmhost.Module) -> None:
    backend = wasmhost.get_backend()
    if not backend.supports("memory.grow"):
        pytest.skip(f"the {backend.name} backend has no Memory.grow from Python")
    ex = wasmhost.Instance(three).exports
    assert _mem(ex, "b").grow(1) == 2
    assert (_mem(ex, "a").grow(1), len(_mem(ex, "a")), len(_mem(ex, "b"))) == (1, 2 * PAGE, 3 * PAGE)
    assert (ex.size0(), ex.size1(), ex.size2()) == (2, 3, 1)
    with pytest.raises(IndexError):
        _mem(ex, "a").grow(3)  # past its maximum of 4
    assert (len(_mem(ex, "a")), len(_mem(ex, "b"))) == (2 * PAGE, 3 * PAGE)


def test_memory_access_is_checked_per_memory(three: wasmhost.Module) -> None:
    ex = wasmhost.Instance(three).exports
    _mem(ex, "a").write(len(_mem(ex, "a")) - 1, b"\x01")
    with pytest.raises(IndexError):
        _mem(ex, "a").read(len(_mem(ex, "a")) - 1, 2)  # past memory 0, though memory 1 is bigger
    assert _mem(ex, "b").read(len(_mem(ex, "a")) - 1, 2) == b"\0\0"


def test_max_memory_holds_every_memory_the_module_defines(three: wasmhost.Module) -> None:
    ex = wasmhost.Instance(three, max_memory=3).exports
    assert (_mem(ex, "a").type().maximum, _mem(ex, "b").type().maximum) == (3, 3)  # 4 is lowered, none gets the ceiling
    assert (ex.grow0(2), ex.grow0(1)) == (1, -1)  # 1 -> 3 pages, then past it
    assert (ex.grow1(1), ex.grow1(1)) == (2, -1)  # 2 -> 3
    assert (ex.grow2(2), ex.grow2(1)) == (1, -1)  # memory 2 is not exported, and held all the same
    assert (ex.size0(), ex.size1(), ex.size2()) == (3, 3, 3)
    assert (len(_mem(ex, "a")), len(_mem(ex, "b"))) == (3 * PAGE, 3 * PAGE)
    free = wasmhost.Instance(three).exports  # the module itself has no ceiling
    assert (free.grow1(5), free.grow2(5)) == (2, 1)


def test_max_memory_refuses_a_module_that_starts_over_it(three: wasmhost.Module) -> None:
    with pytest.raises(ValueError, match="starts at 2 pages"):
        wasmhost.Instance(three, max_memory=1)  # memory 1 starts at 2 pages


def test_two_imported_memories_are_used_independently(two_imported: wasmhost.Module) -> None:
    m0, m1 = wasmhost.Memory(1, 3), wasmhost.Memory(2, 5)
    ex = wasmhost.Instance(two_imported, {"env": {"m0": m0, "m1": m1}}).exports
    ex.store0(10, 7)
    ex.store1(10, 9)
    assert (ex.load0(10), ex.load1(10)) == (7, 9)
    assert (m0.read(10, 1), m1.read(10, 1)) == (b"\x07", b"\x09")
    m1.write(20, b"\x05")
    assert (ex.load1(20), ex.load0(20)) == (5, 0)
    assert (ex.size0(), ex.size1()) == (1, 2)
    assert (ex.grow1(3), ex.size0(), ex.size1(), len(m0), len(m1)) == (2, 1, 5, PAGE, 5 * PAGE)
    assert (ex.grow0(2), ex.grow0(1)) == (1, -1)  # the maximum of the memory the host gave is the ceiling
    assert (m0.type().maximum, m1.type().maximum) == (3, 5)


def test_swapped_imported_memories_are_a_matter_of_the_import_object(two_imported: wasmhost.Module) -> None:
    m0, m1 = wasmhost.Memory(1), wasmhost.Memory(1)
    ex = wasmhost.Instance(two_imported, {"env": {"m0": m1, "m1": m0}}).exports
    ex.store0(0, 3)
    assert (m1.read(0, 1), m0.read(0, 1)) == (b"\x03", b"\0")
    with pytest.raises(wasmhost.LinkError):
        wasmhost.Instance(two_imported, {"env": {"m0": m0, "m1": 1}})


def test_max_memory_leaves_imported_memories_to_the_host(two_imported: wasmhost.Module) -> None:
    ex = wasmhost.Instance(
        two_imported, {"env": {"m0": wasmhost.Memory(1, 3), "m1": wasmhost.Memory(1, 2)}}, max_memory=3
    ).exports
    assert (ex.grow0(2), ex.grow0(1), ex.grow1(1), ex.grow1(1)) == (1, -1, 1, -1)  # each held by its own maximum
    for memories in ((wasmhost.Memory(1, 3), wasmhost.Memory(1)), (wasmhost.Memory(1, 9), wasmhost.Memory(1, 3))):
        with pytest.raises(wasmhost.LinkError, match="max_memory"):
            wasmhost.Instance(two_imported, {"env": dict(zip(("m0", "m1"), memories, strict=True))}, max_memory=3)


def test_a_module_with_one_memory_is_as_it_was(session: str) -> None:
    ex = wasmhost.Instance(wasmhost.Module(wb.owns_memory(1, 2)), max_memory=3).exports
    assert (ex.memory.type().maximum, ex.grow(1), ex.grow(1)) == (2, 1, -1)
