# S0003: several memories of one instance

Status: draft
Backlog: B-603 (the multi-memory part; `memory64` is not in this spec)

## Goal
The memories of a module that has more than one are reachable from Python, each one, in the order the module numbers them, so that the host of WASI 0.2 (S0001) can give fusedwasi one memory for each component of a fused
module. It is shown by a test on each backend that takes such a module: a module with three memories, read, written, grown and limited through the API, with the answers the table below promises, in a CI run.

## Context
Measured on 2026-11-05 on this machine (Linux, wasmtime-py 49.0.0, Node 22.22.0, Bun 1.4.2, pywasm3 `4c1334e`), one throw-away script, not a CI run (CI will carry the checks of this spec):
* **Exported memories already work.** A module with two exported memories `a` and `b` (and a third, not exported): `Module.exports()` lists both; `inst.exports.a` and `inst.exports.b` are separate `Memory` objects;
  `read`, `write`, `len`, `type()`, `grow` (from Python, and `memory.grow $b` inside the module) act on the right one and leave the other alone. `view` works on wasmtime and wasm3 (as for one memory). Same answers on
  wasmtime, Node, Bun and wasm3, except that wasm3 cannot `grow` from Python (it can't for one memory either).
* **Imported memories work, where an import object can be made.** A module that imports `env.m0` and `env.m1` gets two `Memory` objects from the import object and uses them independently on wasmtime, Node and Bun. wasm3
  can't make a `Memory` on its own (`supports("import.memory")` is "no"), so it can't take imported memories at all.
* **A memory that is neither exported nor imported is not reachable** from Python by any API: the engines' own embedding APIs reach exports and imports only.
* CI (SUPPORTS.md, run of `fde7d0d`): a module with two memories runs on `wasmtime`, `node`, `bun`, `wasm3` and `pyodide`, and **not** on `jsc`, `gi-jsc`, `jscontext` (the engine refuses it).
* The parser keeps the types of all memories in module order (`memory_types`, imports first, as the binary numbers them) and `limit_memory` (`max_memory`) rewrites every memory the module defines; neither has a test
  with more than one memory that this spec knows of.
* What fusedwasi needs (S0001): `Guest.memories`, a list with one memory for each component, indexed by `comp`, or a function that gives the memory (so that one that moves is followed); and the `cabi_realloc` of each component.

## The contract
The API **may need nothing new** for modules whose memories are all exported or imported: each is a `Memory` already. What is open is how the list in module order is made, see the questions. Fixed by this spec whatever the
answer is:
* A memory the module neither exports nor imports is reported, never silently skipped: whoever asks for "memory number N" and it is not reachable gets an error that names the number and says what the module would
  have to export.
* `max_memory` (`limit_memory`) holds every memory the module defines to the limit, not only the first; a test with three memories.
* A backend whose engine refuses a module with several memories says so with the engine's message in a `CompileError`; there is no new `supports` string for it (SUPPORTS.md shows it, from CI).
* No change for a module with one memory.

## Matrix
| Backend | Exported memories | Imported memories | Notes |
|---|---|---|---|
| wasmtime | yes | yes | measured locally |
| node, bun | yes | yes | measured locally; no `view` (as for one memory) |
| wasm3 | yes | no | measured locally; can't make a `Memory` on its own, can't `grow` from Python |
| pyodide | to find out | to find out | CI shows the module runs |
| jsc, gi-jsc, jscontext | no | no | the engine refuses the module (CI) |

## Tests and probes
* a module with three memories (two exported, one imported or defined), on each backend of the matrix: read, write, grow, type, limits of each; the answers above;
* `max_memory` over several memories;
* a probe row `multi-memory-api` in `tests/feature_probes.py`, if the questions are answered so that the API has something to probe beyond the existing module-level `multi-memory` row;
* the self-test step for several memories (it asks `supports` first, and reports the JavaScriptCore family as not supported).

## Out of scope
`memory64`; shared memories; a different API for one memory; anything in fusedwasi; the host of WASI 0.2 itself (S0001).

## Open questions
1. **Is anything new needed?** The memories are `Memory` objects by export name or import name. S0001 needs them as a list in module order. Option A: nothing new in the API; the host of WASI 0.2 builds the list from the
   names of the exports of the fused module (a convention to be read from a real fused module). Option B: an `Instance.memories` list in module order (a thing the JavaScript API does not have; the rule is to stay near it). A is
   smaller; B depends on no naming. Cost of B: the index of an export in the descriptors (`ExportDescriptor` would need an index the JS API lacks), or a list built from the module's memory section; a new name for tests and docs.
2. **Are the memories of a fused module exported at all?** `meld` is not installed here (`wasm-tools` is), so no real fused module has been read. If they are not exported nor imported, S0001 can not run on any
   engine through a JavaScript-style API and the plan for 0.2 has to change (a different engine interface). Read one first.
3. Should the JavaScriptCore family be given a way out (a module with one memory only), or is "not supported" the answer? Out of this spec's reach: the engine refuses the module.

## Changes
