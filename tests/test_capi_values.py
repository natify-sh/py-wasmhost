"""CApi against the real JavaScriptCore library: values, exceptions, nesting, bytes, host functions."""

from __future__ import annotations

import ctypes
from collections.abc import Iterator

import pytest

from wasmhost._capi import CApi, HostCallFailed, load_library  # pyright: ignore[reportPrivateUsage]


@pytest.fixture
def api() -> Iterator[CApi]:
    try:
        lib = load_library()
    except OSError as exc:
        pytest.skip(f"no JavaScriptCore library: {exc}")
    create, release = lib.JSGlobalContextCreate, lib.JSGlobalContextRelease
    create.restype, create.argtypes = ctypes.c_void_p, [ctypes.c_void_p]
    release.restype, release.argtypes = None, [ctypes.c_void_p]
    context = create(None)
    try:
        yield CApi(lib, context)
    finally:
        release(context)


def test_values_as_text(api: CApi) -> None:
    assert api.evaluate("1 + 2") == "3"
    assert api.evaluate("'abc'") == "abc"
    assert api.evaluate("undefined") == "undefined"
    assert api.evaluate("var a = 1; a + 1") == "2"


def test_var_survives_between_calls(api: CApi) -> None:
    api.evaluate("var kept = 41")
    assert api.evaluate("kept + 1") == "42"


def test_exception(api: CApi) -> None:
    with pytest.raises(RuntimeError) as info:
        api.evaluate("throw new Error('boom')")
    assert str(info.value).startswith("[JS] Error: boom")
    assert api.evaluate("1") == "1"  # the context still works


def test_syntax_error(api: CApi) -> None:
    with pytest.raises(RuntimeError) as info:
        api.evaluate("1 +* 2")
    assert str(info.value).startswith("[JS]")


def test_nested_call(api: CApi) -> None:
    api.set_function("hostEval", lambda args: api.evaluate(args[0]), "bad")
    assert api.evaluate("hostEval('6 * 7') + '!'") == "42!"


def test_ring_wraps(api: CApi) -> None:
    for i in range(100):
        assert api.evaluate(f"'v' + {i}") == f"v{i}"


def test_non_ascii_and_line_separator(api: CApi) -> None:
    assert api.evaluate("'héllo 世界'") == "héllo 世界"
    assert api.evaluate("'a b'") == "a b"
    assert api.evaluate("' '.length") == "1"


def test_bytes_round_trip(api: CApi) -> None:
    api.set_global_bytes("blob", b"\x00\x01\xfe\xff")
    assert api.get_bytes("blob") == b"\x00\x01\xfe\xff"
    assert api.get_bytes("blob.subarray(1, 3)") == b"\x01\xfe"
    with pytest.raises(OSError):
        api.get_bytes("{}")


def test_handler_raising_throws_error_string(api: CApi) -> None:
    def handler(args: list[str]) -> str:
        raise HostCallFailed

    api.set_function("hostFail", handler, "the-error")
    assert api.evaluate("try { hostFail(); 'no' } catch (e) { 'caught ' + e }") == "caught the-error"
    with pytest.raises(RuntimeError, match=r"^\[JS\] the-error"):
        api.evaluate("hostFail()")
