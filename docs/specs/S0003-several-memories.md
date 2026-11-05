# S0003: several memories of one instance

Status: approved 2026-11-05 (the owner: Option A, start with S0003)
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
* **Fused modules export their memories (checked 2026-11-05 with `meld` 0.67.0 from PyPI, two toy components).** `meld fuse a.wasm b.wasm` (default `--memory auto`, which always resolves to `multi`) gave a core module
  with two memories, exported as `memory` and `memory$1`, and the functions of the components. wasmhost ran it on wasmtime, Node, Bun and wasm3: `exports["memory$1"]` is a `Memory`; `read`, `write` and the length act on it alone.
  (The attribute form `exports.memory$1` is not valid Python: the dictionary form is the way.) Two things limit the toy: its import `a:pkg/iface.get` was left unresolved by `meld` (it came out as an import of the fused
  module, answered here by a host function), and it is two components with no WASI import.
* **The names are not stable.** wasmext's own runs (`py-wasmext/docs/WASI_COMPONENTS.md`, `docs/experiments/wasi_checks/`) with `meld` 0.64 to 0.65 and `--exports world` show `memory$0` and `cabi_realloc$1`, and the table there says
  the exports are `greet`, `cabi_post`, `memory$0`, `cabi_realloc$1` for the simple component but "both memories and both `cabi_realloc`" for the complex one (500 KB, two memories). So the name of the memory of component N, and
  which memories are exported at all, depend on the version of `meld` and on its export mode. `meld fuse --memory shared --address-rebase` gives one memory but "is unsound if any input grows memory" (`meld docs memory-strategies`).
* What fusedwasi needs (S0001): `Guest.memories`, a list with one memory for each component, indexed by `comp`, or a function that gives the memory (so that one that moves is followed); and the `cabi_realloc` of each component.

## The contract
The API **may need nothing new** for modules whose memories are all exported or imported: each is a `Memory` already. What is open is how the list in module order is made, see the questions. Fixed by this spec whatever the
answer is:
* **Option A is chosen (the owner, 2026-11-05): no new API.** Every memory a module exports or imports is a `Memory` by its name, which already works (Context). The list of the memories of a fused module, in the order of its
  components, and the error for a memory that is neither exported nor imported, belong to the host of WASI 0.2 (S0001), which takes the names from the caller; they are not part of this spec.
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
* no new probe: the API has nothing to probe beyond the module-level `multi-memory` row of `tests/feature_probes.py`;
* the self-test step for several memories (it asks `supports` first, and reports the JavaScriptCore family as not supported).

## Out of scope
`memory64`; shared memories; a different API for one memory; anything in fusedwasi; the host of WASI 0.2 itself (S0001).

## Open questions
1. **Is anything new needed?** *Leaning, 2026-11-05: Option A.* Every memory of a fused module is already a `Memory` by its export name on four backends, so the API needs nothing; what S0001 needs is a way to **name** the memories (an explicit list or a pattern), because the names vary with `meld`. B would not remove that problem, since module order is not the order of components either. Still to be confirmed by the owner. The memories are `Memory` objects by export name or import name. S0001 needs them as a list in module order. Option A: nothing new in the API; the host of WASI 0.2 builds the list from the
   names of the exports of the fused module (a convention to be read from a real fused module). Option B: an `Instance.memories` list in module order (a thing the JavaScript API does not have; the rule is to stay near it). A is
   smaller; B depends on no naming. Cost of B: the index of an export in the descriptors (`ExportDescriptor` would need an index the JS API lacks), or a list built from the module's memory section; a new name for tests and docs.
2. **Are the memories of a fused module exported at all?** *Answered, 2026-11-05:* yes by default (`memory`, `memory$1`, ...), under names that change with the version and mode of `meld`; a real fused module with a WASI import (the complex one of wasmext) is still to be run through wasmhost, since only toy components were fused here.
3. Should the JavaScriptCore family be given a way out (a module with one memory only), or is "not supported" the answer? Out of this spec's reach: the engine refuses the module.

## Changes

* 2026-11-05: built as Option A, no new API. `tests/test_multi_memory.py` (a module with three memories, two exported and one not; two imported memories; `max_memory` over three memories; data segments), the builders
  `three_memories` and `imports_two_memories` in `tests/wasm_builder.py`, and the self-test step "a module with several memories" (`THREE_MEMORIES`; the JavaScriptCore family reports "not available", as documented). The tests skip with
  the engine's `CompileError` message where the module is refused, and without `import.memory` / `memory.grow` where a backend lacks them. `limit_memory` needed no change: the new tests pass on all four backends and fail
  when it is made to touch the first memory only. Run locally on wasmtime, Node, Bun and wasm3; CI on the other backends is still to be read.
