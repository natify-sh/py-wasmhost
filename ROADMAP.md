# wasmhost roadmap

Status: **rewritten 2026-11-04** on the owner's decisions of that day. The detail of every item is in [BACKLOG.md](BACKLOG.md); this file is the direction and the order. What each backend supports today is in
[SUPPORTS.md](SUPPORTS.md), measured by CI. The sister library is [py-wasmext](https://github.com/natify-sh/py-wasmext); its plan does not bind this one.

## The principle

**Take an unmodified WebAssembly module, compiled for a given target, and run it.** Do not tell people how to patch or configure the original sources (the owner, 2026-10-28). For wasmhost that means:
the engine and the WASI host are ours, the module stays as its authors built it. Whatever needs the user to change the module is a gap to write down.

## The decisions (the owner, 2026-11-04)

1. **wasmhost goes its own way.** It is not unified with `py-wasmext` under one `Store`, one backend protocol or one model of instances. The API stays `Instance(module, imports)` over an engine that has its own
   state (wasmtime has a `Store`, wasm3 and the JavaScript engines do not), and `isolated=True` stays the way to ask for a store of its own where the engine has one. wasmext settles its own store (its D46); wasmhost does not take
   its shape and is not a front end of it. The 182 calls of `Instance(` in the tests, examples and README are not touched by any plan.
2. **WASI is `fusedwasi`, 0.1 and 0.2.** `wasmhost.wasi.preview1` already makes one `fusedwasi.p2.State` for the world and a `Guest` for each `imports()`; fusedwasi itself has one `State` and one `Guest` for both
   families (checked 2026-11-05: `fusedwasi.p1.State is fusedwasi.p2.State`), so the sharing of the state between 0.1 and 0.2 is fusedwasi's and not a goal here. The step is to answer the imports of a WASI 0.2 module that is fused to
   one core module (`meld fuse`, or `wasm-tools component unbundle`; its imports are flat `wasi:*` names, which `fusedwasi.signatures.find_import` resolves) from that same `State` ([S0001](docs/specs/S0001-wasi-0.2-on-one-state.md)).
3. **The work is the widening of the support of features**, backend by backend, as [SUPPORTS.md](SUPPORTS.md) shows it. A feature is taken when a real module needs it; each item goes through `supports(...)`, and a
   backend that can not do it says so (`NotImplementedError`), never a silent no-op.

## Where it is

- Runs core modules on `wasmtime`, `wasm3` (pywasm3), `node`, `bun`, `jsc`, `gi-jsc`, `jscontext` and `pyodide`; what an engine can not do is reported as `supports(...) == False`, not faked.
- WASI 0.1 is `wasmhost.wasi.preview1`, a host over **fusedwasi** (0.1.0a1 from PyPI, pure Python), with `wasi_unstable` too.
- Of the proposals of WebAssembly 2.0 and 3.0 most run inside a module on the engines that have them (SUPPORTS.md); the API does not yet carry `v128`, `externref` or a GC reference as a value, and GC types are not added yet.

## What is next, and what each item waits for

| Item | What it is | Waits for |
|---|---|---|
| **WASI 0.2 imports** | the flat `wasi:*` imports of a fused module of 0.2 answered from the `State` of `Preview1` (S0001) | **B-603 first**: a fused module has a memory for each component and fusedwasi takes the list of them, but the API reaches only an exported memory; and the engines: multi-memory runs on wasmtime, Node, Bun, wasm3 and Pyodide, **not on the JavaScriptCore family** (so not in Pythonista) |
| **B-604** | GC types: not added to wasmhost and not tested in it yet (the parser refuses the type forms), while wasmtime, Node and Bun run such a module directly | the parser (`_binary.py`) and tests per backend first; then a model of references in the API, which is the engines' (a GC reference has no Python value) |
| **B-203** | `externref` and `funcref` as values of globals, and across instances | the engines and the API: reference types run inside a module on every backend measured in SUPPORTS.md, but no value of that kind crosses the Python API. Deferred 2026-10-16: no consumer, none expected |
| **B-601** | exceptions: `WebAssembly.Tag` and `WebAssembly.Exception` in the API | the engines that have them (SUPPORTS.md: `exceptions-exnref`, `legacy-exceptions`) |
| **B-602** | SIMD (`v128`) as a value, shared memory and threads | the engines: the JavaScript engines have them, wasm3 has not SIMD; a shared `Memory` is a `NotImplementedError` today |
| **B-603** | `memory64` and multi-memory in the API (multi-memory is the prerequisite of WASI 0.2, S0001) | the engines (SUPPORTS.md: Bun does not run `memory64`); the modules that use them run on the backends that say "yes" there, the API has no 64-bit sizes yet |
| **B-605** | custom page sizes | an engine that takes such a module (none does in SUPPORTS.md) |
| **B-303** | batch `read`/`write` of many regions | nothing: a speed matter, deferred until it is needed |
| **B-503** | a sandbox with `openat` and `dir_fd` | nothing: it is the file system of the WASI host |
| **B-701b**, **B-701c**, **B-701** | Deno, a pure-Python interpreter, Android | nothing in principle; each new backend implements the interface of `Backend` and is probed like the others |

## Open decisions

1. **The shape of WASI 0.2 in wasmhost.** Decided: fused modules, answered from the `State` that `Preview1` holds (S0001; one class or two is its open question). Not decided: whether wasmhost ever takes a real component (the Component Model with its own types) or leaves that to engines
   that have it. Not planned.
2. **The release of wasmhost** with the fix for Pythonista and StaSh (a standard stream with no `.buffer`) waits for the owner's word; fusedwasi, which it depends on, is released.

## Related

- [SUPPORTS.md](SUPPORTS.md): what each backend supports, from CI.
- [BACKLOG.md](BACKLOG.md): every item, with its history.
- The examples were all run on 2026-10-28 (every one works; `jslinux.py` could not be run because its download host was blocked).
