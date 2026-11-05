# Read this first

This page is the briefing for anyone (person or agent) who starts work on this repository. Everything else is reference material: read it when a task needs it, not before. The rules of work are in
[CLAUDE.md](CLAUDE.md).

## What this project is, in one paragraph

**wasmhost runs WebAssembly from Python with the shape of the JavaScript `WebAssembly` API, on whatever engine the platform has.** A *backend* is an engine behind one interface (`wasmhost/_backend.py`):
`wasmtime`, `wasm3` (pywasm3), `node`, `bun`, `jsc` (JavaScriptCore through its C API), `gi-jsc` (WebKitGTK through PyGObject), `jscontext` (an Objective-C `JSContext`, as in Pythonista on iOS) and `pyodide`
(wasmhost inside Pyodide). The same `Module`, `Instance`, `Memory`, `Table`, `Global` run on all of them; what an engine can not do is reported as `backend.supports(...) == False` and a `NotImplementedError`, never
faked. WASI 0.1 is `wasmhost.wasi.preview1`, a host over [fusedwasi](https://github.com/natify-sh/fusedwasi) (pure Python). The main target is **Pythonista on an iPhone** (Python 3.10, standard library only,
no JIT for wasm); the same code must work on CPython, PyPy, free-threaded CPython, Pyodide, Windows, macOS and Linux.

## What it is NOT (read this twice)

* **Not part of the `py-wasmext` / `waboros` family of one model.** The sister projects are [py-wasmext](https://github.com/natify-sh/py-wasmext) (wasm2c, a C core and a store of its own) and
  [waboros](https://github.com/natify-sh/waboros) (a pure-Python compiler). The owner decided on 2026-11-04 that wasmhost **goes its own way**: no shared `Store`, no common backend protocol, not a front end of either. The API stays
  `Instance(module, imports)` over engines that have their own state. Do not bring their designs in.
* **Not an engine.** wasmhost compiles and runs nothing itself; it drives engines. Its own parser (`_binary.py`) only reads imports, exports and types.
* **Not the component model.** WASI 0.2 runs as core modules (one component unbundled, or several fused by `meld`) over fusedwasi's `State` (S0001), not as a Component Model host.
* **Not a place for a second API.** The API follows the JavaScript WebAssembly API as closely as possible (JavaScriptCore is the reference engine); a plain `int`/`float` form keeps working beside any new one.

## The architecture in five lines

```
Module(bytes)  -> _binary.py reads imports / exports / types  -> backend.compile
Instance(module, imports) -> backend.instantiate (host functions, Memory/Table/Global objects, limits)
backend (one per engine, one lock per backend): _native.py (wasmtime, wasm3); the JavaScript engines: _js.py (node, bun), _jsc.py, _capi.py, _pyodide.py (jsc, gi-jsc, jscontext, pyodide)
wasmhost.wasi.preview1.Preview1 -> one fusedwasi.State for the world, a Guest for each imports()
CLI: wasmhost run | bench | self test      self-test: _selftest.py (runs on a device, where CI does not exist)
```

## Where it is, and what is next

* **Done:** the core API on eight backends; globals, memories (several per module) and tables, `Function`s; batches; limits for untrusted code (`max_memory`, `timeout`, `fuel`, `isolated`); async and threads; WASI 0.1 and
  `wasi_unstable` (`Preview1`) and WASI 0.2 of one component (`Preview2`, with the network denied by default) on fusedwasi 0.1.0b2; the CLI (WASI 0.1 and 0.2; `-S` network flags; `-S http` is step C); examples (coreutils, wasm-clang, CPython for WASI, a shell for Pythonista,
  a WASI 0.2 one).
* **What each backend supports now** is in [SUPPORTS.md](SUPPORTS.md), measured by CI (`tests/test_feature_probes.py`), not copied from any site.
* **Next**, per [ROADMAP.md](ROADMAP.md) and [BACKLOG.md](BACKLOG.md): a real application on `Preview2` (CPython for wasip2); several components through `meld`'s
  import map (S0001 path 2); the guide to components (B-608); then GC types (B-604) and the features the engines have and the API lacks (B-601, B-602, memory64, B-605). A feature is taken when a real module needs it.
* **Waiting for the owner:** the release with the Pythonista fix (a standard stream with no `.buffer`); the pull request of the branch `fusedwasi-p1` into `main`.

## Hard rules (short form; the full list is in CLAUDE.md)

* The package depends only on `fusedwasi`. Engines (wasmtime, pywasm3, PyGObject, rubicon-objc) are optional extras or dev dependencies; a backend whose engine is missing says so and is skipped, never a crash.
* Python 3.10 and the standard library only in the package: it must run in Pythonista.
* The work is spec-driven: a change of a contract has an approved spec in `docs/specs/` before the code.
* A feature comes with tests, a self-test step, a probe in SUPPORTS.md and the README/BACKLOG ([BACKLOG.md](BACKLOG.md), "Rule: the self-test ships together with the feature").
* One backend takes one call at a time; no threads by default.
* What an engine can not do is a `NotImplementedError` and `supports(...) == False`, never a silent no-op.
* Measure, do not guess: a claim about what runs where has a CI run behind it.

## Map of the documents

| when you need | read |
|---|---|
| what it is, how to use it | `README.md` |
| the rules of work, the roles of agents | `CLAUDE.md` |
| the direction and the order of work | `ROADMAP.md` |
| every item, its history, the working rules of the owner | `BACKLOG.md` |
| what each backend supports (from CI) | `SUPPORTS.md` |
| the contract of a change, written before the code | `docs/specs/` (index and rules in `docs/specs/README.md`) |
| the WASI host | `README.md` ("WASI"), `src/wasmhost/wasi/preview1.py`, `tests/data/wasi` (the specification's witx files) |
| the examples | `examples/`, `README.md` ("Try it on a device") |

The maintainer writes in Ukrainian; code, comments, commits and documents are in English. When the maintainer is confused, explain it simply and say honestly what was not verified (a device, Windows) and what was a guess.
