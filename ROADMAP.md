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

- **Core API** on eight backends (`wasmtime`, `wasm3`, `node`, `bun`, `jsc`, `gi-jsc`, `jscontext`, `pyodide`; what an engine can not do is `supports(...) == False`, not faked): `Module`, `Instance`, `Memory`, `Table`, `Global`, `Function`, batches, async and threads; **several memories** (S0003; the JavaScriptCore engines refuse such a module); **limits for untrusted code** (`max_memory`, `timeout`, `fuel`, `isolated`, where the engine can).
- **WASI 0.1**: `Preview1` (with `wasi_unstable`) over fusedwasi 0.1.0b3. **WASI 0.2**: `Preview2`, one `State` shared with `Preview1`; the network denied by default; one component (hello, environment, random, exit, TCP sockets), and **several components fused by `meld`** through `import_map=` (S0004, CI green on `baef8b8`; the JavaScriptCore engines run only a `--memory shared` fusion); `wasi:http` incl. `http_check` and `http_send`, run against a real local server (`ab99e81`, plain http; fusedwasi calls it unstable and needs `h11`).
- **Command line**: `wasmhost run` tells a module of 0.2 from one of 0.1, takes `-S inherit-network`, `allow-ip-name-lookup`, `tcp`, `udp`, `http` and `--import-map` (step B, CI green on `8630d47`; step C on `07656d9`); `self test`; `bench`.
- **A real application on `Preview2`**: the official CPython for `wasm32-wasip2` (wasi-sdk 34, no patch), `examples/cpython/run2.py` (`python2.wasm`, 8 MB), CI green on `b50b8aa`; the network is open there by default, `pip` installs from a wheel on `PYTHONPATH` (a folder, a plain-http index; run by hand on wasmtime); no `ssl` in that build. Exit code only 0 or 1. Not verified: https, stdin, another CPython commit, bun/jsc/jscontext/pyodide for the program itself.
- **SUPPORTS.md** is made from the logs of CI (`tests/test_feature_probes.py`, `tools/probe_features.py`). Most WebAssembly 2.0 and 3.0 proposals run inside a module on the engines that have them; the API does not yet carry `v128`, `externref` or a GC reference as a value, and GC types are not added (B-604).

## What is next, in this order

| Step | What it is | Waits for |
|---|---|---|
| **Guide to components (B-608)** | `docs/COMPONENTS.md` and a README section: how to run a component, with examples, the tools (`wasm-tools`, `meld`) and the limits | nothing: unblocked (CPython for wasip2, CI green on `b50b8aa`); it is written from what runs |
| **B-604 / S0002** | GC types: the parser and the probes, then a model of references | an owner's need; the engines are not the obstacle |
| **B-203, B-601, B-602, B-603 (memory64), B-605** | `externref` and `funcref` as values, exceptions in the API, SIMD values and shared memory, 64-bit memories, custom page sizes | the engines and a real module that needs them (SUPPORTS.md shows which engine has what) |
| **B-611** | native extensions of CPython on WASI: wasmhost as the dynamic loader (an experiment shows the wasm level works on wasmtime, node, bun; not wasm3) | the owner's decision and a spec; CPython was not relinked |
| **B-303, B-701x** | batch read and write, Deno / a pure-Python interpreter / Android | nothing in principle |

## Waiting for the owner

- the **pull request** of the branch `fusedwasi-p1` into `main` (87 commits since 2026-10-23, counted 2026-11-05 against `origin/main`);
- the **release** of wasmhost with the Pythonista fix (a standard stream with no `.buffer`) and now `Preview2`;
- a **run on the device** (iPhone, Pythonista): the self-test, which has steps for several memories and for WASI 0.2;

## Related

- [SUPPORTS.md](SUPPORTS.md): what each backend supports, from CI. [BACKLOG.md](BACKLOG.md): every item, with its history. [BRIEF.md](BRIEF.md): what the project is and is not.
- The examples were all run on 2026-10-28 (every one works; `jslinux.py` could not be run because its download host was blocked); `examples/wasi2.py` is the one for WASI 0.2.
