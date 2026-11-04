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
not cross the Python API ([README, "Not yet"](README.md#not-yet)). "not added to wasmhost" is a feature that wasmhost has not added or tested yet: its own parser (`_binary.py`) refuses the module, so the engine was never asked (it may well support the feature itself).

The column "Edition" says which edition of the standard took the proposal in: 1.0 is the 2019 core, 2.0 the 2022 standard (sign extension, non-trapping float to int, multi-value, reference types, bulk
memory, fixed-width SIMD), 3.0 the 2025 one (64-bit memories, multiple memories, GC, typed function references, tail calls, final exception handling with `exnref`, relaxed SIMD, extended constants);
"other" is a proposal that is in none of them.

<!-- probe:begin -->
| WebAssembly feature | Edition | `wasmtime` (wasmtime-py 49.0.0) | `node` (node 22.23.4, node 24.22.1, node 24.22.2) | `bun` (bun 1.4.4) | `wasm3` (pywasm3 0.9.1.dev75+g4c1334e03) | `jsc` | `gi-jsc` | `jscontext` | `pyodide` (pyodide 314.0.7) |
|---|---|---|---|---|---|---|---|---|---|
| mvp | 1.0 | yes | yes | yes | yes | yes | yes | yes | yes |
| mutable-globals | 1.0 | yes | yes | yes | yes | yes | yes | yes | yes |
| sign-extension | 2.0 | yes | yes | yes | yes | yes | yes | yes | yes |
| non-trapping-float-to-int | 2.0 | yes | yes | yes | yes | yes | yes | yes | yes |
| multi-value | 2.0 | yes | yes | yes | yes | yes | yes | yes | yes |
| reference-types | 2.0 | yes | yes | yes | yes | yes | yes | yes | yes |
| bulk-memory | 2.0 | yes | yes | yes | yes | yes | yes | yes | yes |
| simd | 2.0 | yes | yes | yes | no | no (Linux, JIT off); yes (Darwin, Linux) | no (Linux, JIT off); yes (Linux) | yes | yes |
| memory64 | 3.0 | yes | yes | no | yes | no | no | no | yes |
| multi-memory | 3.0 | yes | yes | yes | yes | no | no | no | yes |
| tail-call | 3.0 | yes | yes | yes | yes | yes | yes | yes | yes |
| extended-const | 3.0 | yes | yes | yes | yes | yes | yes | yes | yes |
| relaxed-simd | 3.0 | yes | yes | yes | no | no | no | no | yes |
| exceptions-exnref | 3.0 | yes | yes | yes | yes | yes | yes | yes | yes |
| typed-function-references | 3.0 | yes | yes | yes | yes | yes | yes | yes | yes |
| gc | 3.0 | not added to wasmhost | not added to wasmhost | not added to wasmhost | not added to wasmhost | not added to wasmhost | not added to wasmhost | not added to wasmhost | not added to wasmhost |
| legacy-exceptions | other | no | yes | yes | no | yes | yes | yes | yes |
| threads | other | no | yes | yes | no | no (Darwin); yes (Linux, Linux, JIT off) | yes | no | yes |
| custom-page-sizes | other | no | no | no | no | no | no | no | no |
| wide-arithmetic | other | yes | no | yes | yes | no | no | no | no |

| `supports(...)` | `wasmtime` | `node` | `bun` | `wasm3` | `jsc` | `gi-jsc` | `jscontext` | `pyodide` |
|---|---|---|---|---|---|---|---|---|
| `fuel` | yes | no | no | yes | no | no | no | no |
| `import.global` | yes | yes | yes | no | yes | yes | yes | yes |
| `import.memory` | yes | yes | yes | no | yes | yes | yes | yes |
| `import.table` | yes | yes | yes | no | yes | yes | yes | yes |
| `imports` | yes | yes | yes | yes | yes | no | yes* | yes |
| `isolated` | yes | no | no | yes | no | no | no | no |
| `memory.grow` | yes | yes | yes | no | yes | yes | yes | yes |
| `memory.view` | yes | no | no | yes | no | no | no | no |
| `table.funcs` | yes | yes | yes | no | yes | yes | yes | yes |
| `table.length` | yes | yes | yes | no | yes | yes | yes | yes |
| `table.signatures` | yes | no | no | no | no | no | no | no |
| `threads` | yes | yes | yes | no | no | no | no | no |
| `timeout` | yes | yes | no | yes | no | no | no | no |

| WASI program (`Preview1` runs `wasi_hello`) | `wasmtime` | `node` | `bun` | `wasm3` | `jsc` | `gi-jsc` | `jscontext` | `pyodide` |
|---|---|---|---|---|---|---|---|---|
| `wasi_snapshot_preview1`: arguments, a file in a preopen, `fd_write`, `proc_exit` | yes | yes | yes | yes | yes | no | yes | yes |

\* `jscontext` / `imports`: corrected by hand to "yes" (the owner, 2026-11-05). The first CI run read `features` from the class, and `jscontext` adds `imports` only when its engine starts (`_js.py`); the WASI program ran on it in the same run. The next run (the test now reads the live backend) writes this cell itself.

Measured by CI: 38 different lines of the log, from these combinations:
- `wasmtime`: Darwin, Linux, Windows; CPython 3.10.22, CPython 3.15.2, PyPy 3.11.17
- `node`: Darwin, Linux, Windows; CPython 3.10.22, CPython 3.15.2, PyPy 3.11.17
- `bun`: Darwin, Linux; CPython 3.10.22, CPython 3.15.2, PyPy 3.11.17
- `wasm3`: Darwin, Linux, Windows; CPython 3.15.2
- `jsc`: Darwin, Linux, Linux (JIT off); CPython 3.10.22, CPython 3.12.3, CPython 3.15.2, PyPy 3.11.17
- `gi-jsc`: Linux, Linux (JIT off); CPython 3.12.3
- `jscontext`: Darwin; CPython 3.10.22, CPython 3.15.2
- `pyodide`: Emscripten; CPython 3.14.2
<!-- probe:end -->

## Reading the tables

The notes below are written by hand from the tables and are checked again whenever the tables are written.

From the CI run of `fde7d0d` (all jobs of Tests green). What the tables say:

* **WebAssembly 1.0 and 2.0 run on every backend**, with one exception: `simd`. `wasm3` has no SIMD, and the JavaScriptCore of WebKitGTK **without its JIT** (the CI job that stands in for an iPhone, where wasm gets no JIT) refuses
  it too; with the JIT it runs (`jsc` on macOS and Linux, `jscontext` on macOS).
* **WebAssembly 3.0:** `tail-call`, `extended-const`, `exceptions-exnref` and `typed-function-references` run on all eight backends. `multi-memory` runs everywhere except the JavaScriptCore family (`jsc`, `gi-jsc`,
  `jscontext`), so not in Pythonista. `memory64` is refused by Bun and by the JavaScriptCore family; `relaxed-simd` by `wasm3` and by the JavaScriptCore family. `gc` is not added to wasmhost (B-604): its cells say nothing about the engines.
* **Other proposals:** `legacy-exceptions` (`try`/`catch`) runs on every backend except `wasmtime` and `wasm3`; `threads` (a shared memory and atomics inside the module) on `node`, `bun`, `pyodide` and on `gi-jsc` / `jsc` on
  Linux, not on `wasmtime`, `wasm3`, `jscontext` and `jsc` on macOS; `wide-arithmetic` on `wasmtime`, `bun` and `wasm3`; `custom-page-sizes` on none.
* **The Node column has three versions** (22.23.4 on Linux, 24.22.x on macOS and Windows); they gave the same answers.
* **Where a cell lists platforms**, the runs disagreed: `jsc` / `gi-jsc` ran both with the JIT and with `JSC_useJIT=false`, and the cell names the run without the JIT. The WebKitGTK run without the JIT is a stand-in for iOS, not iOS itself: `jscontext`
  on a Mac is a real JSContext with the JIT on.
* **Windows, PyPy and the Python versions** (3.10, 3.15, 3.15t, PyPy 3.11) gave the same answers as Linux for `wasmtime`, `node` and `wasm3`; the list under the tables names every combination that was run.

**`supports(...)`**: written from the first run, with the one cell marked `*` corrected; the paragraph about it is written after the next run.

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
