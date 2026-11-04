# What wasmhost supports on each backend

This is the support of **wasmhost's features on each runtime**, as CI measured it: not a list of what an engine could do in general, but what runs through wasmhost on that backend, on that operating system.

Every job of [tests.yml](.github/workflows/tests.yml) runs the suite once per backend, and the suite has one test, `tests/test_feature_probes.py`, that prints one line to the log of the job:
`WASMHOST-SUPPORTS {...}` with the engine and its version, the OS and the Python, the strings of `backend.supports(...)`, whether a WASI program ran, and the answer of every probe
(`tests/feature_probes.py`). The tables below are made from those lines by `tools/probe_features.py`:

```
uv run python tools/probe_features.py --collect <logs of a CI run> --update SUPPORTS.md
```

When the OSes or the Pythons of one backend disagree, the cell says so (`yes (Linux, macOS); no (Windows)`). The last line under the tables names the runs they come from.

## How a WebAssembly feature is probed

A probe is a small module that really uses the feature (its WAT is in `tests/feature_probes.py` beside the bytes). It is given to `wasmhost.Module` and `Instance` on the backend, its export `f` is called, and the
answer must be the one the feature gives; a module that an engine skips over without failing is caught by that, and wasm3, which compiles a function when it is first called, is caught by the call.
"yes" is that the module runs through wasmhost on that backend: what the engine accepts and does with the feature **inside the module**. A value of type `v128`, `externref` or a GC reference still can
not cross the Python API ([README, "Not yet"](README.md#not-yet)). "no, parser of wasmhost" is that wasmhost's own parser (`_binary.py`) refused the module and the engine was never asked.

The column "Edition" says which edition of the standard took the proposal in: 1.0 is the 2019 core, 2.0 the 2022 standard (sign extension, non-trapping float to int, multi-value, reference types, bulk
memory, fixed-width SIMD), 3.0 the 2025 one (64-bit memories, multiple memories, GC, typed function references, tail calls, final exception handling with `exnref`, relaxed SIMD, extended constants);
"other" is a proposal that is in none of them.

<!-- probe:begin -->
<!-- probe:end -->

## Reading the tables

The notes below are written by hand from the tables and are checked again whenever the tables are written.

*(to be filled from the first CI run that carries the probe)*

## WASI

The last row of the tables above is measured: one small WASI program (`tests/wasm_builder.wasi_hello`: arguments, a file made in a preopen, `fd_write`, `proc_exit`) run by `Preview1` on each backend. A
backend that can not take host functions (`imports` is "no" in the `supports(...)` table) can not run a WASI program, since a program imports its functions. The rest is what the code and the specification
files in `tests/data/wasi` say:

| WASI | wasmhost | Notes |
|---|---|---|
| `wasi_snapshot_preview1` (0.1) | yes: all 46 functions, `wasmhost.wasi.preview1.Preview1`, over `fusedwasi` | checked against the specification's witx files; the self-test runs a WASI program on every backend |
| `wasi_unstable` (the first snapshot) | yes: 45 functions (no `sock_accept`) | the same `Preview1` offers both; older toolchains (wasienv, wasm-clang) produce it |
| files | yes: preopens of real folders; `..` and links that leave a folder are `ENOTCAPABLE`; `readonly=` | on POSIX walked with `openat`; on Windows the check and the open are two steps |
| standard streams, arguments, environment, clocks, random | yes | `thread_cputime_id` reads the process clock on Pyodide |
| sockets | no: `ENOTSOCK` | |
| signals | no: `ENOSYS` | `proc_raise` does not end the program here (it does in `wasmext`) |
| `poll_oneoff` that sleeps | yes, but outside what `timeout` and `fuel` can stop | |
| WASI 0.2 (`wasi:*` interfaces, Component Model) | **not yet.** A module of 0.2 fused to one core module has flat `wasi:*` imports, which `fusedwasi` knows (`fusedwasi.p2`); wasmhost does not offer them | the plan: `fusedwasi` 0.1 and 0.2 over one state, see [ROADMAP.md](ROADMAP.md) |
| WASI 0.3 (async) | no | out of scope |
| wasi-threads | no | needs a shared memory first |
