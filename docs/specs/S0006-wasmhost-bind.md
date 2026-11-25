# S0006: `wasmhost bindgen`, generated Python glue for a core wasm module

Status: approved 2026-11-25 (owner). Written 2026-11-24 on `claude/wasmhost-bind-research` from main `60ac793`; the spike (`docs/experiments/s0006_dwarf_spike/`) came before approval; implementation not started.
Backlog: new item, to be numbered by the owner

## Goal
After this, `wasmhost bindgen libfoo.wasm -o foo/` writes a Python package `foo/` that loads the module through wasmhost and gives it Python signatures: `lib = foo.Lib(); lib.parse(b"x", 1)`, with the C types (`uint32_t`, `size_t`, `const char *`, structs with fields, callbacks) taken from the module's own DWARF. A user runs the generated package with the standard library and wasmhost only.

Verified when: a CI job builds a small C library and a small Rust library with debug info, runs `wasmhost bindgen` on each, imports the generated package, and calls every bound function on the backends listed in the Matrix; a stripped build of the same code gives the same generated package as the debug build (same names, types and code hash).

## Context
Facts, checked on main at `60ac793`:
* `src/wasmhost/_binary.py` reads imports and exports with their `FuncType`, memories, tables, globals, and keeps every custom section as `ModuleInfo.custom` (name, bytes), in order. `Module.customSections(m, name)` returns them (`_api.py:854`). So the raw DWARF bytes are already reachable from Python, without a new parser of the binary.
* There is no DWARF reader. A DWARF reader is new code: abbreviation table, DIEs, the forms used by clang/rustc/zig, LEB128, `.debug_str` (and `.debug_str_offsets` for DWARF 5). Only type information is needed (no line tables, no locations).
* The CLI (`_cli.py`) has `version`, `self`, `run`, `bench`, `help`. `bindgen` is a new subcommand.
* The idea and its arguments are in [docs/wasmhost-bind-note.md](../wasmhost-bind-note.md) (maintainer, 2026-11-16). This spec turns it into a contract and asks the questions it leaves open.

Why not the existing tools (from their documented behaviour, not measured here): `ctypesgen` and `autopxd2` read C headers (ctypesgen with a preprocessor and its own parser, autopxd2 with pycparser) and generate ctypes or Cython glue. They need the source text, and they do not see the ABI of the built `.wasm` (sizes and offsets after the compiler, the real export names, which functions are really exported). `bindgen` reads what the compiler produced: the module's exports and imports, and the layout the compiler computed (`DW_AT_byte_size`, `DW_AT_data_member_location`). The source language does not matter as long as its FFI is the wasm32 BasicCABI (C, C++ `extern "C"`, Rust `extern "C"`/`#[repr(C)]`, Zig `export`).

## The contract

### Command line
```
wasmhost bindgen MODULE.wasm -o DIR [--ship STRIPPED.wasm] [--decl FILE.py] [--functions NAME,...]
```
* writes `DIR/__init__.py` (the glue), `DIR/__init__.pyi` (types for pyright), and `DIR/<module>.wasm` (the input, or `--ship` if given);
* `--ship` must export the same names and have the same function signatures as `MODULE.wasm`; `bindgen` checks that and refuses otherwise;
* `--decl` gives ABI types by hand for a module with no DWARF (see below);
* without `--functions`, every exported function that DWARF describes is bound; a function that is exported but not described is listed in the generated docstring as raw (see below).
* exit status 0 on success; a refusal (mismatch, unsupported DWARF, missing export) is an error message and a non-zero status, and no files are written.

### What is read, in order
1. The module's exports and imports (`Module.exports`, `Module.imports`), with `FuncType`.
2. The custom section `.debug_info` with `.debug_abbrev`, `.debug_str`, and for DWARF 5 `.debug_str_offsets`, through `Module.customSections`.
3. Each `DW_TAG_subprogram` with `DW_AT_external` and a name that matches an export (or `DW_AT_export_symbols` / `DW_AT_linkage_name` where the compiler gives them): its parameters and return type are built into ABI types, and then `AbiFuncType.lower()` is compared with the module's own `FuncType`. A difference is an error of `bindgen`.

### DWARF subset
Versions 4 and 5 (see question 1). Tags read: `base_type`, `pointer_type`, `const_type`, `volatile_type`, `typedef`, `structure_type`, `union_type`, `enumeration_type`, `subroutine_type`, `array_type`, `member`, `enumerator`, `subprogram`, `formal_parameter`, `subrange_type`. Attributes read: the ones these tags need (name, byte_size, encoding, type, data_member_location, upper_bound/count, const_value, external, declaration). Any other tag or form is **reported** in the bindgen's output as "not read: <tag>", and the entity that needs it is left out, never guessed.

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
* the glue records the hash of the code section of the `.wasm` it was generated for; `Lib()` refuses a different module with `ValueError`. A stripped `--ship` build gets the same hash (checked by `bindgen` at generation time).
* a call with a string argument uses `instance.batch()` where the backend supports it (malloc, write, call, read, free as one trip); otherwise it uses single calls. Both give the same results (tested).

### Modules that cannot be bound fully
* **No DWARF:** the raw mode from `FuncType` (ints and floats only), or `--decl FILE.py`, which holds `AbiFuncType` and `ABI` declarations written by the user. `bindgen` checks the declarations against the module's `FuncType` in both directions.
* **Rust structs without `#[repr(C)]`:** DWARF gives a layout that may change between compiler versions. `bindgen` warns and generates the glue, with the warning in its docstring.
* **Languages with their own object model** (TinyGo, AssemblyScript, wasm GC languages): out of scope for this spec. A module of these gets the raw mode or nothing; their data is not in linear memory in the way `bindgen` needs.

### What does not change
* the public API of wasmhost; `bindgen` is a command and a generator, and the generated glue uses only the API that exists now (`Module`, `Instance`, `Memory`, `Table`, `Function`, `batch`);
* `supports(...)` strings: none added; `bindgen` does not need a backend feature that is missing (see Matrix);
* the dependency rule of CLAUDE.md changes for one thing: `pyelftools` (pinned) becomes a **regular dependency** of the package, imported by `bindgen` (the owner, 2026-11-24, in CLAUDE.md). Every install of wasmhost gets it, `bindgen` or not; it is pure Python, so it installs on Pythonista as wasmhost does.

## Matrix
The glue runs on backends that have the features it uses. Rows are what must be true for the generated package's tests; "not run" means not run here and not in CI, and it is said as such in the report.

| Backend | Done by | Expected | Notes |
|---|---|---|---|
| wasmtime | `bindgen` generation and the glue's tests | pass | the reference |
| wasm3 | the glue's tests | pass | `Memory.view` available |
| node | the glue's tests | pass | struct fields through copies |
| bun | the glue's tests | pass | as node |
| jsc | the glue's tests | expected to pass; check | macOS segfault in BACKLOG is open; not a blocker for `bindgen` itself |
| gi-jsc | the glue's tests | expected to pass; check | |
| jscontext | the glue's tests | expected to pass; check | |
| pyodide | the glue's tests | not required | `bindgen` runs in CPython; the glue runs where wasmhost runs |

`bindgen` runs wherever its `.wasm` is, the device included: the source of the glue is the ready module, not the source code, so generation on Pythonista is a requirement, not an option. The owner decided (2026-11-24) not to test on the device separately: CI is the check. The cost of the read on a large DWARF section on the device is not measured; it is a known, accepted risk. `pyelftools` is pure Python and is installed on the device the same way as wasmhost.

## Tests and probes
* `tests/test_bind_dwarf.py`: the DWARF reader on a small set of hand-made `.debug_*` bytes and on real clang and rustc output (built in CI, see below); each tag read; a refused tag is reported.
* `tests/test_bind_generate.py`: `wasmhost bindgen` on the two test libraries; the generated `__init__.py` imports and runs on every backend in the Matrix that is installed; struct fields; a callback; a cstr argument; a mismatch between DWARF and `--decl` is refused; `--ship` with a different export set is refused.
* `tests/test_bind_debug_vs_strip.py`: the same source built with `-g` and stripped gives the same generated names, types and code hash.
* test libraries (the owner's decision: C, Zig and Rust in v1): `tests/data/bind/c_lib.c` built with wasi-sdk (`-g -mexec-model=reactor`), `tests/data/bind/zig_lib.zig` built with `zig build-lib -target wasm32-wasi` and `export fn`, `tests/data/bind/rust_lib/` built with `wasm32-wasip1` and `extern "C"`. All built in CI, not checked in as binaries.
* **Self-test:** none for the generation (it does not run on the device). If the generated glue's runtime needs a step on the device, that is a second step, decided with the owner after the first version.
* **Probe:** none in `tests/feature_probes.py` (no new engine feature). SUPPORTS.md is not changed.
* CI jobs that must be green: Tests (on every OS and Python), Pre-commit, and a new job that builds the two test libraries and runs `bindgen` on them.

## Out of scope
* a component-model or WIT source (WIT is for an interface designed anew; `bindgen` keeps the module's own ABI);
* WASI auto-detection (the note's "theoretical extension"); `bindgen` writes glue that takes an optional import object for now;
* `externref` (its own spec, if wanted: question 3);
* wasm GC types (S0002);
* a generator for other languages' bindings, a C header output, Cython output;
* changes to the parser in `_binary.py` beyond what is needed to pass custom sections (none needed so far).

## Open questions
1. **DWARF versions: decided (owner, 2026-11-24): 4 and 5 for C and Zig; Rust on DWARF 4 only (owner, 2026-11-25).** Zig DWARF 5 was not measured by the spike (zig 0.17.1 has no flag found for it); the first implementation step settles it or reports it.
2. **Struct access: decided (owner, 2026-11-24): classes** with properties over `Memory.view` / `read`.
3. **`externref`:** its own spec (S0007?), or left out. `bindgen` does not need it for C or Rust structs. Not answered yet.
4. **Rust in the first version: decided (owner, 2026-11-24): yes, on DWARF 4 (owner, 2026-11-25).** Test languages of v1: C, Zig, Rust. The spike built Rust DWARF 5 only with `RUSTC_BOOTSTRAP=1`; CI does not use that flag.
5. **Where the tests run: decided (owner, 2026-11-24): CI only. No separate device step in v1; the owner expects it to work on Pythonista (native, iPhone 16), and the CI result is the check.**

Decided by the owner (2026-11-24): the name is `bindgen`; `pyelftools` is a regular dependency (see "What does not change") and is the DWARF reader, so no own reader is written in v1.

Before implementation: a spike (three small libraries in C, Zig and Rust built with `-g`, read through pyelftools, the DIEs and forms recorded, and the time and memory of the read on CPython; the device is not part of the spike by the owner's decision). The spike decides whether the status of this spec moves from draft to approved.

## Changes
2026-11-24: draft written from the research on `claude/wasmhost-bind-research`; no code.
2026-11-24: the owner decided the name (`bindgen`) and the dependency (`pyelftools`, regular, pinned); CLAUDE.md changed to match.
2026-11-24: the owner decided DWARF 4 and 5, classes for structs, Rust in v1 with C and Zig; the device run is native on an iPhone 16. Open: question 3 (`externref`). The spike comes before the spec is approved.
2026-11-25: the owner approved the spec; Rust stays on DWARF 4. The spike is committed in `docs/experiments/s0006_dwarf_spike/` (measurement only): pyelftools 0.33 read C (DWARF 4, 5), Rust (4, 5) and Zig (4); CPython 3.13 read time 1.4-4.7 ms for 0.3-1.7 KB of `.debug_info`, 167 ms for 206 KB (Zig Debug). Not run: Zig DWARF 5, wasm32-wasip1 std builds, C++.
