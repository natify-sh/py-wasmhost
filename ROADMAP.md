# wasmhost roadmap

Status: **updated 2026-11-05**. The detail of every item is in [BACKLOG.md](BACKLOG.md); this file is the direction and the order. What each backend supports today is in [SUPPORTS.md](SUPPORTS.md), measured by CI;
the contract of every change is a spec in [docs/specs/](docs/specs/README.md). The sister library is [py-wasmext](https://github.com/natify-sh/py-wasmext); its plan does not bind this one.

## The principle

**Take an unmodified WebAssembly module, compiled for a given target, and run it.** Do not tell people how to patch or configure the original sources (the owner, 2026-10-28). For wasmhost that means:
the engine and the WASI host are ours, the module stays as its authors built it. Whatever needs the user to change the module is a gap to write down.

## The decisions (the owner, 2026-11-04 and 2026-11-05)

1. **wasmhost goes its own way.** It is not unified with `py-wasmext` under one `Store`, one backend protocol or one model of instances. The API stays `Instance(module, imports)` over an engine that has its own state, and
   `isolated=True` stays the way to ask for a store of its own where the engine has one.
2. **WASI is `fusedwasi`, 0.1 and 0.2.** One `fusedwasi.State` is the world of both: `Preview1` and `Preview2` expose it (`state`) and take it (`state=`). WASI 0.2 comes in two paths ([S0001](docs/specs/S0001-wasi-0.2-on-one-state.md)):
   **one component** (what `wasm-tools component unbundle` leaves, or `meld fuse` of one: one memory) first, which runs on every backend with host functions, JavaScriptCore included; **several components fused by `meld`**
   (a memory for each, so multi-memory, which JavaScriptCore does not have) after it, driven by `meld`'s import map.
3. **The network is denied by default.** `network`, `socket_addr_check` and the like open it in the library; `wasmhost run` takes the flags of Wasmtime's `-S` group (`-S inherit-network`, `-S tcp`, ...).
4. **The work is spec-driven** (`docs/specs/`: a contract is approved before the code) and **the support of features is widened backend by backend**, as SUPPORTS.md shows it; a feature is taken when a real module needs it.

## Where it is (2026-11-05)

- Runs core modules on `wasmtime`, `wasm3` (pywasm3), `node`, `bun`, `jsc`, `gi-jsc`, `jscontext` and `pyodide`; what an engine can not do is `supports(...) == False`, not faked.
- **WASI 0.1**: `wasmhost.wasi.Preview1` over fusedwasi 0.1.0b2 (with `wasi_unstable`). **WASI 0.2, one component**: `wasmhost.wasi.Preview2` (S0001 step A, built): hello, environment, random, exit, and TCP sockets with the
  network denied by default; shown by the tests on every backend that takes host functions.
- **Several memories** (S0003, built): every exported or imported memory of a module is its own `Memory`; `max_memory` holds all of them; the JavaScriptCore engines refuse such a module (their message is in the spec).
- **SUPPORTS.md** is made from the logs of CI (`tests/test_feature_probes.py`, `tools/probe_features.py`).
- Of the proposals of WebAssembly 2.0 and 3.0 most run inside a module on the engines that have them; the API does not yet carry `v128`, `externref` or a GC reference as a value, and GC types are not added to wasmhost yet.

- **The command line for WASI 0.2** (S0001 step B, built, CI green on `8630d47`): `wasmhost run` tells a module of 0.2 from one of 0.1 by its imports and takes the `-S` flags `inherit-network`, `allow-ip-name-lookup`, `tcp`, `udp` as in Wasmtime (`http` waits for fusedwasi).

## What is next, in this order

| Step | What it is | Waits for |
|---|---|---|
| **A real application on `Preview2`** | CPython built for `wasm32-wasip2` (wasi-sdk 34), unbundled, run through `Preview2`: the proof that it is more than small examples | the owner's go; the build of CPython may need patches |
| **S0001 path 2** | several components: `Preview2` reads `meld`'s import map (`comp` is the `memory.index` of an import; the `$N` of a name is stripped); not for JavaScriptCore | S0003 (done); a run with real WASI calls through the map (the one made so far called none) |
| **Guide to components (B-608)** | `docs/COMPONENTS.md` and a README section: how to run a component, with examples, the tools (`wasm-tools`, `meld`) and the limits | the application above; written from what runs |
| **`wasi:http`, `-S http`** | `Preview2` serving `wasi:http`, and the flag | fusedwasi: its `wasi:http` is in progress, not ready |
| **B-604 / S0002** | GC types: the parser and the probes, then a model of references | an owner's need; the engines are not the obstacle |
| **B-203, B-601, B-602, B-603 (memory64), B-605** | `externref` and `funcref` as values, exceptions in the API, SIMD values and shared memory, 64-bit memories, custom page sizes | the engines and a real module that needs them (SUPPORTS.md shows which engine has what) |
| **B-303, B-503, B-701x** | batch read and write, an `openat` sandbox, Deno / a pure-Python interpreter / Android | nothing in principle |

## Waiting for the owner

- the **pull request** of the branch `fusedwasi-p1` into `main` (a few dozen commits since 2026-10-23);
- the **release** of wasmhost with the Pythonista fix (a standard stream with no `.buffer`) and now `Preview2`;
- a **run on the device** (iPhone, Pythonista): the self-test, which has steps for several memories and for WASI 0.2.

## Related

- [SUPPORTS.md](SUPPORTS.md): what each backend supports, from CI. [BACKLOG.md](BACKLOG.md): every item, with its history. [BRIEF.md](BRIEF.md): what the project is and is not.
- The examples were all run on 2026-10-28 (every one works; `jslinux.py` could not be run because its download host was blocked); `examples/wasi2.py` is the one for WASI 0.2.
