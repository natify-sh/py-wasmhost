---
title: wasmhost bind - a CLI entry that generates Python glue for C libraries compiled to core wasm modules, types from the module's own DWARF
kind: note for the orchestrator of py-wasmhost
status: idea from the maintainer (2026-11-16): a CLI entry in wasmhost itself; needs a spec before code
date: 2026-11-16
checked against: py-wasmhost main at da2c7a7
---

# `wasmhost bind`: generated glue over wasmhost, from the `.wasm` alone

## The idea (maintainer, 2026-11-16)

The aim is something like cffi's out-of-line mode for C libraries compiled to WebAssembly, as **a
command of wasmhost itself**, next to `wasmhost run` and `wasmhost bench`. It reads **one input, a
core wasm module** (no component model, no WIT), and writes a plain Python module, the **glue**.
The glue loads the `.wasm` through wasmhost and wraps its functions, structs and callbacks with C
meaning: signedness, strings, pointers, struct fields.

```
wasmhost bind libfoo.wasm -o foo/
  -> foo/__init__.py    the glue: a Lib class, struct classes, callback helpers
  -> foo/__init__.pyi   types for pyright and IDEs
  -> foo/libfoo.wasm    (or the stripped build given with --ship)
```

The analogy is `dlopen` for `.so` against `waopen` for `.wasm`. wasmhost already reads the binary in
Python; `bind` reads it further. Its C types come from the module's own DWARF, so it needs:
* no C parser;
* no declarations written by hand;
* no new dependency: it stays within the rule "`fusedwasi` and the standard library".

The glue needs only wasmhost at run time (Python 3.10, standard library; Pythonista).

### Why not WIT / `wasmtime bindgen`

These serve the opposite case: an interface designed anew as a component. WIT cannot express what
existing C APIs are made of:
* raw pointers, out-parameters and caller-filled buffers;
* function pointers with `void *userdata`;
* unions, bit fields and self-referential structs;
* varargs and control of memory layout.

The canonical ABI also copies strings and lists. `bind` keeps the C ABI as it is (clang's wasm32 C
ABI, WebAssembly tool-conventions "BasicCABI").

## Where the types come from

**From the wasm sections**, which `_binary.py` already reads:
* which functions are exported, under which names (`export_name` may differ from the C name);
* the imports (C calling Python);
* each `FuncType`, against which the DWARF types are checked;
* `memory`, `malloc`/`free`, `__indirect_function_table`, `_initialize`.

**From DWARF** (`clang -g`: `.debug_info`, `.debug_abbrev`, `.debug_str` and, for DWARF 5,
`.debug_str_offsets`), read through `Module.customSections(module, name)`:
* the exact C types of each function's parameters and result, `typedef` names included
  (`uint32_t`, `size_t`), signedness, pointers, `const char *`;
* **structs with the offsets, size and alignment clang computed** (`DW_AT_data_member_location`,
  `DW_AT_byte_size`). The wasm32 layout rules do not have to be reproduced;
* `enum` with the names of its values, `union`, bit fields;
* function-pointer types with their signatures (callbacks);
* parameter names, so the glue reads like the header: `def parse(self, s: bytes, n: int) -> int`.

**The reader.** A DWARF reader in the standard library: the abbreviation table, DIEs, LEB128, the
forms, and strings from `.debug_str`. Only types are needed: no line tables, locations or
expressions. That is a few hundred lines. Rough estimate; the spec should bound it.

**Generate from a debug build, ship a stripped one.**
* `bind` runs on the developer's machine on `libfoo.wasm` built with `-g`. The wheel ships the
  `wasm-strip` / `llvm-strip` version.
* `-g` does not change code at the same `-O`. To be checked in the spec's tests: compare the code
  sections of both builds.
* The glue can record a hash of the code section, so that `Lib()` checks it loads the module it
  was generated for.

**Without DWARF**:
* the **raw mode** still works from `FuncType` alone (ints and floats, as wasmhost calls functions
  today);
* for someone else's module with no DWARF, **declarations in Python** (the same `CType` /
  `CFuncType` objects below) are the fallback input: `--decl decl.py`.

## What wasmhost already gives (main at da2c7a7)

| the glue needs | wasmhost has |
|---|---|
| export and import signatures, checked against DWARF at generation time | `Module.exports(module)`, `Module.imports(module)` with `FuncType` |
| DWARF and any other custom section | `Module.customSections(module, name)` |
| strings, buffers, struct fields | `memory.read` / `memory.write` everywhere; `Memory.view(offset, length)` with no copy on wasmtime and wasm3 |
| function pointers (callbacks) | `Table.set(i, f)` / `grow(n, f)` with a `Function`; a C function pointer is an index into `__indirect_function_table` |
| C calling Python | host functions in the import object |
| a declared signature that is wrong | `Function.signature` / `type()`, refused rather than obeyed |
| cheap calls on JavaScript engines | `instance.batch()`: malloc, write, call, read and free as one trip, with `i32` arithmetic on `Ref` for offsets |

**Batches matter most.** A C call with a string argument is five steps. On Pythonista (`jsc`
through `objc_util`) each step is a bridged call. The glue can always emit the batch form: on
wasmtime and wasm3 a batch runs in Python and costs nothing extra.

## The model, in wasmhost's own shape

The command and the glue use C types shaped like wasmhost's. DWARF is read into them; `--decl`
writes them by hand.

* **`CType(str)`, like `ValueType`.** The type equals its name and its `repr` is the bare name.
  Each type carries:
  * its wasm type at the boundary (`uint8`/`uint32`/pointers/`cstr` are `i32`; `int64`/`uint64`
    are `i64`);
  * its size and alignment (from DWARF);
  * its conversion (unsigned results, `cstr` copied in and out of memory).

  Use C's names (`int32`, `uint32`, `float`, `double`), so they do not shadow wasmhost's
  `i32`/`i64`/`f32`/`f64`.
* **`CFuncType(parameters, results)`, like `FuncType`.** `lower()` gives the `FuncType` and is
  checked against the module's export or import type, both directions:
  * exports: Python calls C;
  * imports: C calls Python.

  A mismatch between DWARF (or a declaration) and the module is an error of `bind`, not of a call.
* **Values stay `int` and `float`.** A pointer is an `int` offset. Struct access goes through a
  view on memory at an offset (`struct.unpack_from` / `pack_into` on `Memory.view`, or a copy
  through `read` on engines without a view), not a wrapper value type. This follows the rule
  "no wrapper value types".
* **C globals** (`extern int counter;`) live in linear memory. An exported data symbol is a wasm
  global holding its address; DWARF gives its type.

### Conventions the module must follow (to document for users)

* built as a **reactor** (`-mexec-model=reactor`): `_initialize` is called once, like a
  library's constructors;
* exports named (`export_name`, `--export`, or `--export-dynamic`);
* `memory` exported;
* `malloc` and `free` exported when the glue must allocate;
* `__indirect_function_table` exported when the library takes callbacks;
* WASI imports answered by wasmhost's `Preview1` when the library uses libc I/O;
* built with `-g` for `bind`. DWARF 4 and 5 both appear in practice; the spec says which `bind`
  reads first.

### WASI auto-detection (theoretical, not a goal of a first version)

In theory `bind` could detect WASI by itself instead of asking the user for a flag. The module says
what it needs in its imports: `wasi_snapshot_preview1` for WASI 0.1, and `wasi:*@0.2.N` names for a
0.2 core module (what `wasm-tools component unbundle` leaves). wasmhost already tells the two apart
for `wasmhost run` (`src/wasmhost/wasi/_flavor.py`, S0005 `wasi.for_module`). The generator could
use the same check at generation time and then:
* emit glue that builds `Preview1` or `Preview2` and passes it as the import object, with no
  `wasi=` option for the user;
* list in the glue's docstring which WASI capabilities the library imports (files, clock, random,
  sockets), so that the user sees what the library will ask of the host;
* leave the network and the file system closed by default, as `wasmhost run` does, and expose them
  as parameters of the glue's constructor (a preopened directory, `-S` style flags).

Unchecked: whether a library built with only a few WASI imports (for example `fd_write` for
`printf`) is better served by a minimal host function than by a whole `Preview1`; and how a
detection should treat a module that imports WASI 0.1 and 0.2 at once. A mismatch is an error of
`bind`, as for the C types.

## What is missing in wasmhost (does not block a first version)

* **`externref`** in tables, globals and values. clang's `__externref_t` cannot cross the boundary
  until wasmhost carries it, for every backend.
* **`Memory.view` on the JavaScript engines.** There, struct fields are read through copies. In a
  batch this is acceptable.
* **GC types** (S0002, draft). Not needed for C: C data lives in linear memory.

## For the spec (`docs/specs/S0006-...`, approved before code)

* **The command line:** `wasmhost bind MODULE -o DIR`, `--ship STRIPPED.wasm`, `--decl FILE`,
  and what is bound (every exported function DWARF describes, or a list).
* **The generated module's API:** `Lib(imports=..., backend=...)`, methods, struct classes, the
  callback helper, errors.
* **The DWARF subset read:** versions, forms, and the type tags (`base_type`, `pointer_type`,
  `const_type`, `typedef`, `structure_type`, `union_type`, `enumeration_type`, `subroutine_type`,
  `array_type`, `member`, `subprogram`, `formal_parameter`). Anything else is reported, not
  guessed.
* **Tests:**
  * a small C library built with wasi-sdk in CI;
  * its glue generated and run on every backend that can;
  * `-g` against stripped code identity;
  * a DWARF/`FuncType` mismatch refused.
* **The self-test:** whether a step for the glue's run time belongs on the device (the
  generation itself does not run there).
* **README and BACKLOG** entries; SUPPORTS.md is not affected (no new engine feature).

## Questions for the owner

1. **The first DWARF version** to read: DWARF 5 (current clang default) only, or 4 and 5.
2. **Struct access:** classes with properties over `Memory.view` / `read` (suggested), or plain
   functions per field.
3. **`externref` in wasmhost:** whether it gets its own spec. `bind` needs it only for
   `__externref_t`, and it is useful on its own (JavaScript API parity).

Another engine behind `Backend` (for example a pure-Python JIT) would serve the generated glue with
no change to it. That would be a backend question for wasmhost's own specs, not a part of `bind`.
