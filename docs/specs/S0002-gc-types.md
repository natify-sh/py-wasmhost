# S0002: GC types

Status: draft
Backlog: B-604

## Goal
A module that declares struct and array types and uses the GC instructions loads and runs through wasmhost on the backends whose engines take it, and the others say so (`NotImplementedError` or `supports(...) == False`).
It is shown by the probe `gc` in `tests/feature_probes.py` going from "not added to wasmhost" to "yes" on those backends in SUPPORTS.md, taken from CI.

## Context
* GC is **not added to wasmhost and not tested in it** (the owner, 2026-11-04). `_binary.py` knows no GC type forms, so a module with a struct or array type is refused with `unsupported type form` before the engine is asked.
* Checked locally on 2026-11-04 (one module: a struct made with `struct.new` and read with `struct.get`, answer 7): wasmtime-py 49.0.0, Node 22.22.0 and Bun 1.4.2 run it directly; the Python 3.14 wasm3 build refuses it (`unsupported type form`
  also came from wasmhost's parser, so the wasm3 result is not known). The jsc family and Pyodide were not run.
* The API carries no value of a GC reference type; whether and how it should is a question below.

## The contract
*To be written after the questions below are answered.* The first part is internal: `_binary.py` reads the GC type forms (struct, array, rec groups, sub types) and the value types that name them, so that imports, exports and
types of such a module can be described; nothing in the public API changes. The second part, a model of references in the API, is a separate spec.

## Matrix
| Backend | Done by | Expected | Notes |
|---|---|---|---|
| wasmtime | | yes | the engine runs it directly |
| node, bun | | yes | the engine runs it directly |
| wasm3 | | no | to find out once the parser reads the forms; pywasm3 main has no GC (SUPPORTS.md probe) |
| jsc, gi-jsc, jscontext, pyodide | | to find out | by the CI probe |

## Tests and probes
* `_binary.py` reads a module with each GC form (a table-driven test of the bytes);
* the probe `gc` on every backend; the cell changes in SUPPORTS.md from the CI run;
* a test that a backend without GC reports it and does not fail with an engine message.

## Out of scope
GC references as values crossing the Python API; `externref`/`funcref` values (B-203); the other 3.0 proposals.

## Open questions
1. Is the first part (the parser only) worth shipping alone, or only together with a model of references?
2. A GC reference in an export's signature (`(result (ref null $t))`): refuse the call, or hand Python an opaque handle?

## Changes
