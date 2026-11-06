# ruff: noqa: E501
"""Small modules, one for each WebAssembly feature, and the answer each gives when the engine really does what the feature says (`tests/test_feature_probes.py` runs them on the
backend that pytest was started with and prints one line, which `tools/probe_features.py` collects from the logs of CI into SUPPORTS.md).

The bytes are made from the WAT next to them by `uv run python tools/probe_features.py --regenerate` (wasmtime's `wat2wasm`); they are kept here so that a job without wasmtime (JavaScriptCore,
Pyodide) can run them. Every module exports `f: () -> i32`; wasm3 compiles a function when it is first called, so a probe has to call it, and the answer must be the one the feature gives, so
that an engine that skips an opcode it does not know does not pass."""

from __future__ import annotations

# name: (edition of the standard that took the proposal in: "1.0", "2.0", "3.0", or "other"; answer of f; bytes; the WAT they were made from)
PROBES: dict[str, tuple[str, int, bytes, str]] = {
    "mvp": (
        "1.0",
        2,
        bytes.fromhex(
            "0061736d010000000105016000017f030201000404017000010503010001070501016600000a09010700410141016a0b"
        ),
        '(module (memory 1) (table 1 funcref) (func (export "f") (result i32) i32.const 1 i32.const 1 i32.add))',
    ),
    "mutable-globals": (
        "1.0",
        1,
        bytes.fromhex(
            "0061736d010000000105016000017f030201000606017f0141010b07090201670300016600000a0601040023000b000b046e616d65070401000167"
        ),
        '(module (global $g (export "g") (mut i32) (i32.const 1)) (func (export "f") (result i32) global.get $g))',
    ),
    "sign-extension": (
        "2.0",
        -1,
        bytes.fromhex("0061736d010000000105016000017f03020100070501016600000a0801060041ff01c00b"),
        '(module (func (export "f") (result i32) i32.const 255 i32.extend8_s))',
    ),
    "non-trapping-float-to-int": (
        "2.0",
        2147483647,
        bytes.fromhex("0061736d010000000105016000017f03020100070501016600000a0b01090043ec78ad60fc000b"),
        '(module (func (export "f") (result i32) f32.const 1e20 i32.trunc_sat_f32_s))',
    ),
    "multi-value": (
        "2.0",
        3,
        bytes.fromhex(
            "0061736d01000000010a026000027f7f6000017f0303020001070501016600010a0e020600410141020b050010006a0b000b046e616d65010401000167"
        ),
        '(module (func $g (result i32 i32) i32.const 1 i32.const 2) (func (export "f") (result i32) call $g i32.add))',
    ),
    "reference-types": (
        "2.0",
        1,
        bytes.fromhex("0061736d010000000105016000017f030201000404016f0002070501016600000a07010500d06fd10b"),
        '(module (table 2 externref) (func (export "f") (result i32) ref.null extern ref.is_null))',
    ),
    "bulk-memory": (
        "2.0",
        1,
        bytes.fromhex(
            "0061736d010000000105016000017f030201000503010001070501016600000a10010e00410041004100fc0a000041010b"
        ),
        '(module (memory 1) (func (export "f") (result i32) i32.const 0 i32.const 0 i32.const 0 memory.copy i32.const 1))',
    ),
    "simd": (
        "2.0",
        2,
        bytes.fromhex(
            "0061736d010000000105016000017f03020100070501016600000a2e012c00fd0c01000000020000000300000004000000fd0c01000000010000000100000001000000fdae01fd1b000b"
        ),
        '(module (func (export "f") (result i32) v128.const i32x4 1 2 3 4 v128.const i32x4 1 1 1 1 i32x4.add i32x4.extract_lane 0))',
    ),
    "memory64": (
        "3.0",
        9,
        bytes.fromhex(
            "0061736d010000000105016000017f030201000503010401070501016600000a10010e004208410936020042082802000b"
        ),
        '(module (memory i64 1) (func (export "f") (result i32) i64.const 8 i32.const 9 i32.store i64.const 8 i32.load))',
    ),
    "multi-memory": (
        "3.0",
        50,
        bytes.fromhex(
            "0061736d010000000105016000017f0302010005050200010001070501016600000a1b01190041004105364201004100280200410028420100410a6c6a0b000e046e616d65060702000161010162"
        ),
        '(module (memory $a 1) (memory $b 1) (func (export "f") (result i32) i32.const 0 i32.const 5 i32.store $b i32.const 0 i32.load $a i32.const 0 i32.load $b i32.const 10 i32.mul i32.add))',
    ),
    "tail-call": (
        "3.0",
        1,
        bytes.fromhex(
            "0061736d010000000105016000017f0303020000070501016600010a0b02040041010b040012000b000b046e616d65010401000167"
        ),
        '(module (func $g (result i32) i32.const 1) (func (export "f") (result i32) return_call $g))',
    ),
    "extended-const": (
        "3.0",
        3,
        bytes.fromhex(
            "0061736d010000000105016000017f030201000609017f00410141026a0b070501016600000a0601040023000b000b046e616d65070401000167"
        ),
        '(module (global $g i32 (i32.add (i32.const 1) (i32.const 2))) (func (export "f") (result i32) global.get $g))',
    ),
    "relaxed-simd": (
        "3.0",
        1,
        bytes.fromhex(
            "0061736d010000000105016000017f03020100070501016600000a1c011a00fd0c0000803f000000400000404000008040fd8102fd1b000b"
        ),
        '(module (func (export "f") (result i32) v128.const f32x4 1 2 3 4 i32x4.relaxed_trunc_f32x4_s i32x4.extract_lane 0))',
    ),
    "exceptions-exnref": (
        "3.0",
        1,
        bytes.fromhex(
            "0061736d010000000108026000006000017f030201010d03010000070501016600000a1401120002401f4001020008000b41000f0b41010b0013046e616d6503060100010001680b0401000174"
        ),
        '(module (tag $t) (func (export "f") (result i32) (block $h (try_table (catch_all $h) throw $t) i32.const 0 return) i32.const 1))',
    ),
    "typed-function-references": (
        "3.0",
        1,
        bytes.fromhex(
            "0061736d010000000105016000017f030302000007050101660001090501030001000a0d02040041010b0600d20014000b0011046e616d65010401000167040401000174"
        ),
        '(module (type $t (func (result i32))) (func $g (type $t) i32.const 1) (elem declare func $g) (func (export "f") (result i32) ref.func $g call_ref $t))',
    ),
    "gc": (
        "3.0",
        7,
        bytes.fromhex(
            "0061736d010000000109025f017f006000017f03020101070501016600000a0d010b004107fb0000fb0200000b000b046e616d65040401000173"
        ),
        '(module (type $s (struct (field i32))) (func (export "f") (result i32) i32.const 7 struct.new $s struct.get $s 0))',
    ),
    "legacy-exceptions": (
        "other",
        1,
        bytes.fromhex(
            "0061736d010000000108026000006000017f030201010d03010000070501016600000a0f010d00067f08004100070041010b0b000b046e616d650b0401000174"
        ),
        '(module (tag $t) (func (export "f") (result i32) try (result i32) throw $t i32.const 0 catch $t i32.const 1 end))',
    ),
    "threads": (
        "other",
        6,
        bytes.fromhex(
            "0061736d010000000105016000017f03020100050401030101070501016600000a1201100041004106fe1702004100fe1002000b"
        ),
        '(module (memory 1 1 shared) (func (export "f") (result i32) i32.const 0 i32.const 6 i32.atomic.store i32.const 0 i32.atomic.load))',
    ),
    "custom-page-sizes": (
        "other",
        1,
        bytes.fromhex("0061736d010000000105016000017f03020100050401080100070501016600000a0601040041010b"),
        '(module (memory 1 (pagesize 1)) (func (export "f") (result i32) i32.const 1))',
    ),
    "wide-arithmetic": (
        "other",
        4,
        bytes.fromhex("0061736d010000000105016000017f03020100070501016600000a10010e004201420242034204fc131aa70b"),
        '(module (func (export "f") (result i32) i64.const 1 i64.const 2 i64.const 3 i64.const 4 i64.add128 drop i32.wrap_i64))',
    ),
}


def run(backend: str) -> dict[str, str]:
    """Each probe on the backend: "yes" when `f` answers as the feature says, "parser" when wasmhost's own parser refuses the module (the engine was never asked), else "no"."""
    import wasmhost

    result: dict[str, str] = {}
    for name, (_edition, expected, data, _wat) in PROBES.items():
        try:
            instance = wasmhost.Instance(wasmhost.Module(data, backend=backend), {})
            got = instance.exports.f()  # type: ignore[attr-defined]
            result[name] = "yes" if got == expected else "no"
        except BaseException as exc:  # noqa: BLE001 -- any failure is a "no"; the message is kept in the line of the log
            result[name] = "parser" if "unsupported type form" in str(exc) else "no"
    return result
