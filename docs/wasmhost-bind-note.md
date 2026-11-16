---
title: wasmhost bind - a CLI entry that generates Python glue for C libraries compiled to core wasm modules
kind: note for the orchestrator of py-wasmhost
status: idea from the maintainer (2026-11-16): a CLI entry in wasmhost itself; needs a spec before code
date: 2026-11-16
checked against: py-wasmhost main at da2c7a7
---

# `wasmhost bind`: generated glue over wasmhost

## The idea (maintainer, 2026-11-16)

The aim is something like cffi's out-of-line mode for C libraries compiled to WebAssembly, as **a
command of wasmhost itself**, next to `wasmhost run` and `wasmhost bench` (the maintainer, 2026-11-16:
not a separate package). Run on the developer's machine, it reads two inputs:
* a **core** wasm module (no component model, no WIT);
* the library's C header.

It writes a plain Python module, the **glue**, that loads the `.wasm` through wasmhost and wraps
its functions, structs and callbacks with C meaning: signedness, strings, pointers, struct fields.

```
wasmhost bind libfoo.wasm --header foo.h -o foo/
  -> foo/__init__.py    the glue: a Lib class, struct classes, callback helpers
  -> foo/__init__.pyi   types for pyright and IDEs
  -> foo/libfoo.wasm
```

The analogy is `dlopen` for `.so` against `waopen` for `.wasm`. The glue needs only wasmhost at run
time: Python 3.10 and the standard library, as on Pythonista. The C parser and any DWARF reading
are needed at generation time only.

### The dependency rule

wasmhost depends only on `fusedwasi` and the standard library. A C parser does not fit that. The
options:

1. **An optional extra `wasmhost[bind]` with pycparser** (suggested). Without it, `wasmhost bind`
   says which extra to install. This is the rule's pattern for engines, applied to a tool. It is an
   extension of the rule: the owner decides.
2. **wasmhost's own parser for a subset of C headers**, standard library only: prototypes,
   `struct`, `typedef`, `enum`, fixed-width types. It covers most APIs; full C (macros, `#include`)
   needs a preprocessor, and that is its cost.
3. **Types from the module only**: DWARF read through `Module.customSections`, standard library
   only. No header is needed, but a DWARF reader is larger than a C subset, and without `-g` there
   are no types.

Suggested: (1) first, (3) later as the fallback when there is no header.

### Why not WIT / `wasmtime bindgen`

These serve the opposite case: an interface designed anew as a component. WIT cannot express what
existing C APIs are made of:
* raw pointers, out-parameters and caller-filled buffers;
* function pointers with `void *userdata`;
* unions, bit fields and self-referential structs;
* varargs and control of memory layout.

The canonical ABI also copies strings and lists. `bind` keeps the C ABI as it is (clang's wasm32
C ABI, WebAssembly tool-conventions "BasicCABI").

## What wasmhost already gives (main at da2c7a7)

Nothing has to change in wasmhost to start.

| the glue needs | wasmhost has |
|---|---|
| export and import signatures, to check them against the header at generation time | `Module.exports(module)`, `Module.imports(module)` with `FuncType` |
| types from the module itself when there is no header | `Module.customSections(module, name)`: a custom section the build adds, or DWARF (`.debug_info`) from `clang -g` |
| strings, buffers, struct fields | `memory.read` / `memory.write` everywhere; `Memory.view(offset, length)` with no copy on wasmtime and wasm3 |
| function pointers (callbacks) | `Table.set(i, f)` / `grow(n, f)` with a `Function`; a C function pointer is an index into `__indirect_function_table` |
| C calling Python | host functions in the import object |
| a declared signature that is wrong | `Function.signature` / `type()`, refused rather than obeyed |
| cheap calls on JavaScript engines | `instance.batch()`: malloc, write, call, read and free as one trip, with `i32` arithmetic on `Ref` for offsets |

**Batches matter most.** A C call with a string argument is five steps. On Pythonista (`jsc`
through `objc_util`) each step is a bridged call. The glue can always emit the batch form: on
wasmtime and wasm3 a batch runs in Python and costs nothing extra.

## The model, in wasmhost's own shape

The command and the glue use their own C types, shaped like wasmhost's:

* **`CType(str)`, like `ValueType`.** The type equals its name and its `repr` is the bare name.
  Each type carries:
  * its wasm type at the boundary (`u8`/`u32`/`ptr`/`cstr` are `i32`; `i64`/`u64` are `i64`);
  * its size and alignment in wasm32 (a pointer and a `long` are 4 bytes);
  * its conversion (unsigned results, `cstr` copied in and out of memory).

  The C names should not shadow wasmhost's `i32`/`i64`/`f32`/`f64`: put them in their own
  namespace or use C's names.
* **`CFuncType(parameters, results)`, like `FuncType`.** `lower()` gives the `FuncType` and is
  checked against the module's export or import type, both directions:
  * exports: Python calls C;
  * imports: C calls Python.
  A mismatch is an error of the generator, not of a call.
* **Values stay `int` and `float`.** A pointer is an `int` offset. Struct access goes through a
  view on memory at an offset (`struct.unpack_from` / `pack_into` on `Memory.view`, or a copy
  through `read` on engines without a view), not a wrapper value type. This follows the rule
  "no wrapper value types".
* **C globals** (`extern int counter;`) live in linear memory. An exported data symbol is a wasm
  global holding its address.

### Conventions the module must follow (to document for users)

* built as a **reactor** (`-mexec-model=reactor`): `_initialize` is called once, like a
  library's constructors;
* exports named (`export_name`, `--export`, or `--export-dynamic`);
* `memory` exported;
* `malloc` and `free` exported when the glue must allocate;
* `__indirect_function_table` exported when the library takes callbacks;
* WASI imports answered by wasmhost's `Preview1` when the library uses libc I/O.

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
detection should treat a module that imports WASI 0.1 and 0.2 at once. A mismatch is an error of the
generator, as for the C types.

## What is missing in wasmhost (does not block a first version)

* **`externref`** in tables, globals and values. clang's `__externref_t` cannot cross the boundary
  until wasmhost carries it, for every backend.
* **`Memory.view` on the JavaScript engines.** There, struct fields are read through copies. In a
  batch this is acceptable.
* **GC types** (S0002, draft). Not needed for C: C data lives in linear memory.

## Questions for the owner

1. **The dependency rule** (above): the extra `wasmhost[bind]` with pycparser, an own C subset
   parser, or DWARF only.
2. **The spec.** `wasmhost bind` is a new capability, so it needs `docs/specs/S0006-...` approved
   before code. In the spec: the command line, the generated module's API, the type model, the
   module conventions, the tests (a small C library built with wasi-sdk in CI, its glue run on
   every backend) and a self-test step if the glue's run time belongs on the device.
3. **`externref` in wasmhost.** Whether it gets its own spec. `bind` needs it only for
   `__externref_t`, and it is useful on its own (JavaScript API parity).

Another engine behind `Backend` (for example a pure-Python JIT) would serve the generated glue with
no change to it. That would be a backend question for wasmhost's own specs, not a part of `bind`.
