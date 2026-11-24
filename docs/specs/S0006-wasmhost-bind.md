# S0006: `wasmhost bind`, generated Python glue for a core wasm module

Status: draft (2026-11-24, written on `claude/wasmhost-bind-research` from main `60ac793`; not read by the owner yet)
Backlog: new item, to be numbered by the owner

## Goal
After this, `wasmhost bind libfoo.wasm -o foo/` writes a Python package `foo/` that loads the module through wasmhost and gives it Python signatures: `lib = foo.Lib(); lib.parse(b"x", 1)`, with the C types (`uint32_t`, `size_t`, `const char *`, structs with fields, callbacks) taken from the module's own DWARF. A user runs the generated package with the standard library and wasmhost only.

Verified when: a CI job builds a small C library and a small Rust library with debug info, runs `wasmhost bind` on each, imports the generated package, and calls every bound function on the backends listed in the Matrix; a stripped build of the same code gives the same generated package as the debug build (same names, types and code hash).

## Context
Facts, checked on main at `60ac793`:
* `src/wasmhost/_binary.py` reads imports and exports with their `FuncType`, memories, tables, globals, and keeps every custom section as `ModuleInfo.custom` (name, bytes), in order. `Module.customSections(m, name)` returns them (`_api.py:854`). So the raw DWARF bytes are already reachable from Python, without a new parser of the binary.
* There is no DWARF reader. A DWARF reader is new code: abbreviation table, DIEs, the forms used by clang/rustc/zig, LEB128, `.debug_str` (and `.debug_str_offsets` for DWARF 5). Only type information is needed (no line tables, no locations).
* The CLI (`_cli.py`) has `version`, `self`, `run`, `bench`, `help`. `bind` is a new subcommand.
* The idea and its arguments are in [docs/wasmhost-bind-note.md](../wasmhost-bind-note.md) (maintainer, 2026-11-16). This spec turns it into a contract and asks the questions it leaves open.

Why not the existing tools (from their documented behaviour, not measured here): `ctypesgen` and `autopxd2` read C headers (ctypesgen with a preprocessor and its own parser, autopxd2 with pycparser) and generate ctypes or Cython glue. They need the source text, and they do not see the ABI of the built `.wasm` (sizes and offsets after the compiler, the real export names, which functions are really exported). `bind` reads what the compiler produced: the module's exports and imports, and the layout the compiler computed (`DW_AT_byte_size`, `DW_AT_data_member_location`). The source language does not matter as long as its FFI is the wasm32 BasicCABI (C, C++ `extern "C"`, Rust `extern "C"`/`#[repr(C)]`, Zig `export`).

## The contract

### Command line
```
wasmhost bind MODULE.wasm -o DIR [--ship STRIPPED.wasm] [--decl FILE.py] [--functions NAME,...]
```
* writes `DIR/__init__.py` (the glue), `DIR/__init__.pyi` (types for pyright), and `DIR/<module>.wasm` (the input, or `--ship` if given);
* `--ship` must export the same names and have the same function signatures as `MODULE.wasm`; `bind` checks that and refuses otherwise;
* `--decl` gives ABI types by hand for a module with no DWARF (see below);
* without `--functions`, every exported function that DWARF describes is bound; a function that is exported but not described is listed in the generated docstring as raw (see below).
* exit status 0 on success; a refusal (mismatch, unsupported DWARF, missing export) is an error message and a non-zero status, and no files are written.

### What is read, in order
1. The module's exports and imports (`Module.exports`, `Module.imports`), with `FuncType`.
2. The custom section `.debug_info` with `.debug_abbrev`, `.debug_str`, and for DWARF 5 `.debug_str_offsets`, through `Module.customSections`.
3. Each `DW_TAG_subprogram` with `DW_AT_external` and a name that matches an export (or `DW_AT_export_symbols` / `DW_AT_linkage_name` where the compiler gives them): its parameters and return type are built into ABI types, and then `AbiFuncType.lower()` is compared with the module's own `FuncType`. A difference is an error of `bind`.

### DWARF subset
Versions 4 and 5 (see question 1). Tags read: `base_type`, `pointer_type`, `const_type`, `volatile_type`, `typedef`, `structure_type`, `union_type`, `enumeration_type`, `subroutine_type`, `array_type`, `member`, `enumerator`, `subprogram`, `formal_parameter`, `subrange_type`. Attributes read: the ones these tags need (name, byte_size, encoding, type, data_member_location, upper_bound/count, const_value, external, declaration). Any other tag or form is **reported** in the bind's output as "not read: <tag>", and the entity that needs it is left out, never guessed.

### ABI types (the model)
Like `ValueType`, a `str` subclass whose `repr` is its name: `int8` ... `uint64`, `float32`, `float64`, `bool`, `cstr`, `ptr(T)`, `Struct`, `Array`, `FuncPtr`, `Enum`. Each carries:
* the wasm type at the boundary (`int8`..`uint32`, `bool`, pointers, `cstr` are `i32`; `int64`/`uint64` are `i64`; `float32`/`float64` are `f32`/`f64`);
* its size and alignment, from DWARF;
* its conversion (unsigned results as `int` >= 0, `cstr` copied in and out of memory).

`AbiFuncType(parameters, results)` is `FuncType`-like; `lower()` returns the `FuncType`. A pointer is an `int` offset. Struct fields are read and written through `struct.unpack_from` / `pack_into` on `Memory.view` (or `read`/`write` where there is no view). No wrapper value type; the plain `int` and `float` form of a call keeps working.

### The generated module's API
```python
import foo
lib = foo.Lib()                       # loads libfoo.wasm next to __init__.py; backend=... and imports=... optional
lib.parse(b"abc", 3) -> int           # an export, with the Python types from DWARF
lib.strlen(b"x") -> int               # cstr argument: copied into memory, freed after the call
p = lib.make_point(1, 2)              # returns a foo.Point (a struct class over memory at a pointer)
p.x, p.y                              # fields: properties over the memory
lib.run_with_callback(cb, None)       # cb: a Python function; FuncPtr argument: a Table slot is set and freed after the call
lib.close()
```
* a struct class holds `(lib, ptr)`; it does not own memory unless the function that returned it says so (a `malloc`ed result is freed by `lib.free(p)` only when the user asks);
* a callback is a Python callable wrapped into a `Function` put in `__indirect_function_table` for the call;
* the glue records the hash of the code section of the `.wasm` it was generated for; `Lib()` refuses a different module with `ValueError`. A stripped `--ship` build gets the same hash (checked by `bind` at generation time).
* a call with a string argument uses `instance.batch()` where the backend supports it (malloc, write, call, read, free as one trip); otherwise it uses single calls. Both give the same results (tested).

### Modules that cannot be bound fully
* **No DWARF:** the raw mode from `FuncType` (ints and floats only), or `--decl FILE.py`, which holds `AbiFuncType` and `ABI` declarations written by the user. `bind` checks the declarations against the module's `FuncType` in both directions.
* **Rust structs without `#[repr(C)]`:** DWARF gives a layout that may change between compiler versions. `bind` warns and generates the glue, with the warning in its docstring.
* **Languages with their own object model** (TinyGo, AssemblyScript, wasm GC languages): out of scope for this spec. A module of these gets the raw mode or nothing; their data is not in linear memory in the way `bind` needs.

### What does not change
* the public API of wasmhost; `bind` is a command and a generator, and the generated glue uses only the API that exists now (`Module`, `Instance`, `Memory`, `Table`, `Function`, `batch`);
* `supports(...)` strings: none added; `bind` does not need a backend feature that is missing (see Matrix);
* the dependency rule: no new dependency; the DWARF reader is in the standard library.

## Matrix
The glue runs on backends that have the features it uses. Rows are what must be true for the generated package's tests; "not run" means not run here and not in CI, and it is said as such in the report.

| Backend | Done by | Expected | Notes |
|---|---|---|---|
| wasmtime | `bind` generation and the glue's tests | pass | the reference |
| wasm3 | the glue's tests | pass | `Memory.view` available |
| node | the glue's tests | pass | struct fields through copies |
| bun | the glue's tests | pass | as node |
| jsc | the glue's tests | expected to pass; check | macOS segfault in BACKLOG is open; not a blocker for `bind` itself |
| gi-jsc | the glue's tests | expected to pass; check | |
| jscontext | the glue's tests | expected to pass; check | |
| pyodide | the glue's tests | not required | `bind` runs in CPython; the glue runs where wasmhost runs |

`bind` itself (generation) runs in CPython only; it is not on the device (Pythonista) in its first version, but the glue is.

## Tests and probes
* `tests/test_bind_dwarf.py`: the DWARF reader on a small set of hand-made `.debug_*` bytes and on real clang and rustc output (built in CI, see below); each tag read; a refused tag is reported.
* `tests/test_bind_generate.py`: `wasmhost bind` on the two test libraries; the generated `__init__.py` imports and runs on every backend in the Matrix that is installed; struct fields; a callback; a cstr argument; a mismatch between DWARF and `--decl` is refused; `--ship` with a different export set is refused.
* `tests/test_bind_debug_vs_strip.py`: the same source built with `-g` and stripped gives the same generated names, types and code hash.
* test libraries: `tests/data/bind/c_lib.c` built with wasi-sdk (`-g -mexec-model=reactor`), `tests/data/bind/rust_lib/` built with `wasm32-wasip1` and `extern "C"`. Both built in CI, not checked in as binaries.
* **Self-test:** none for the generation (it does not run on the device). If the generated glue's runtime needs a step on the device, that is a second step, decided with the owner after the first version.
* **Probe:** none in `tests/feature_probes.py` (no new engine feature). SUPPORTS.md is not changed.
* CI jobs that must be green: Tests (on every OS and Python), Pre-commit, and a new job that builds the two test libraries and runs `bind` on them.

## Out of scope
* a component-model or WIT source (WIT is for an interface designed anew; `bind` keeps the module's own ABI);
* WASI auto-detection (the note's "theoretical extension"); `bind` writes glue that takes an optional import object for now;
* `externref` (its own spec, if wanted: question 3);
* wasm GC types (S0002);
* a generator for other languages' bindings, a C header output, Cython output;
* a backend for Pythonista's device run of `bind`; generation runs in CPython;
* changes to the parser in `_binary.py` beyond what is needed to pass custom sections (none needed so far).

## Open questions
1. **DWARF versions:** DWARF 5 only (current clang and rustc default), or 4 and 5 (suggested: 4 and 5, because the reader's cost is mostly in the forms, and older toolchains still appear).
2. **Struct access:** classes with properties over `Memory.view` / `read` (proposed above), or plain functions per field.
3. **`externref`:** its own spec (S0007?), or left out. `bind` does not need it for C or Rust structs.
4. **Rust in the first version:** the Rust test library from the start (proposed), or C first.
5. **Where the glue's tests run:** only CI, or also a self-test step on the device (proposed: CI only for the first version).
6. **Name:** `bind` as proposed, or `wasmhost gen`. The note uses `bind`.

## Changes
2026-11-24: draft written from the research on `claude/wasmhost-bind-research`; no code.
