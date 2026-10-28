# wasmhost roadmap

Status: **written 2026-10-28** from the owner's statement of the same day and from [BACKLOG.md](BACKLOG.md) (the detail of every item is there; this file is the order and the open decisions). The sister library is [py-wasmext](https://github.com/natify-sh/py-wasmext); its plan is `docs/WASI_TARGET_PLAN.md` and its reason for WASI 0.2 is `docs/why_wasi_p2.md`. Lines marked **my reading** are a reading of the backlog and have not been decided with the owner.

## The principle

**Take an unmodified WebAssembly module, compiled for a given target, and run it.** Do not tell people how to patch or configure the original sources (the owner, 2026-10-28). For wasmhost that means: the engine and the WASI host are ours, the module stays as its authors built it. Whatever needs the user to change the module is a gap to write down.

## Where it is

- Runs core modules on `wasmtime`, `wasm3` (pywasm3), `node`, `bun`, `jsc`, `gi-jsc`, `jscontext` and `pyodide`; what an engine cannot do is reported as `supports(...) == False`, not faked.
- WASI 0.1 is `wasmhost.wasi.preview1`, a host over **fusedwasi** (0.1.0a1 from PyPI, pure Python): one `fusedwasi.p2.State` for the world and a `Guest` for each `imports()`.
- **There is no store.** The state of instances, memories, tables and functions lives in each engine (wasmtime has its own `Store`, wasm3 and the JS engines do not), and the API is `Instance(module, imports)`. That is why passing a function, a table or a value between instances and modules is as good as the weakest engine and is not one model.
- 182 occurrences of `Instance(` in the tests, the examples, the README and the backlog (counted 2026-10-28): the cost of any change of that call.

## The order (the owner, 2026-10-28)

1. **First py-wasmext is finished**: the store, `Function` (funcref), `externref`, the registry of owners of tables and functions (C2b/C2c), the tags of exceptions (C6), the shared runtime across artifacts (C7). Together they are what makes the passing of values between instances and modules possible there.
2. **Then the store of wasmhost, on the side of the Python library** (stage 7 of the plan of wasmext). It has to be built over the engines, since most of them have none, and it takes the **shape** that wasmext settled, so that there are not two models of one thing.
3. **Then the features that wait for it** (the table below).

Nothing in this file is scheduled before step 1 is done.

## What waits for what

| Item | What it is | Waits for (my reading) |
| --- | --- | --- |
| **B-203** | `externref` and `funcref` as values of globals, and across instances | the store and the registry of owners (steps 1 and 2). Deferred on 2026-10-16: no consumer, none expected |
| **B-601** | exceptions: `WebAssembly.Tag` and `WebAssembly.Exception` in the API | the store (a tag has **one identity in the store**, C6 in wasmext) and the engines that have them |
| **B-602** | SIMD (`v128`), shared memory and threads | the engines, not the store: the JS engines have it, wasm3 does not |
| **B-603** | `memory64` and multi-memory | the engines (Safari has no multi-memory); the store only for the model of several memories of one instance |
| **B-604** | GC types | the engines and a model of references that the store brings |
| **B-605** | custom page sizes | the engines |
| **B-303** | batch `read`/`write` of many regions | nothing: a speed matter, deferred until it is needed |
| **B-503** | a sandbox with `openat` and `dir_fd` | nothing: it is the file system of the WASI host |
| **B-701b**, **B-701c**, **B-701** | Deno, a pure-Python interpreter, Android | nothing in principle; each new backend will have to implement whatever small interface the store asks of an engine |

## Open decisions

1. **The shape of the store in wasmhost.** In wasmext the store is required and there is no implicit one (the owner dropped the idea of a private store of each instance); whether wasmhost does the same, and so changes the 182 calls, or keeps `Instance(module, imports)` as a shortcut, is **not decided**.
2. **WASI 0.2 in wasmhost.** Today only 0.1. A module of 0.2 fused to one core module (`meld fuse`, or `wasm-tools component unbundle`) has flat `wasi:*` imports that fusedwasi already knows: its neutral tests bind them on wasmtime-py and on pywasm3 (`tests/neutral/` in fusedwasi) and it was run on 2026-10-28. Whether wasmhost takes that on, and how it would hand the user a module of 0.2 without asking them to fuse it by hand, is **not decided** and **not planned**.
3. **The release of wasmhost** with the fix for Pythonista and StaSh (a standard stream with no `.buffer`) waits for the owner's word; fusedwasi, which it depends on, is released.

## Related

- [BACKLOG.md](BACKLOG.md): every item, with its history.
- The examples were all run on 2026-10-28 (every one works; `jslinux.py` could not be run because its download host was blocked; `wasmclang.py` was broken by `imports()` being called once for each name, and is fixed).
