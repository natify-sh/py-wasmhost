# What wasmhost supports on each backend

This is the support of **wasmhost's features on each runtime**, as CI measured it: not a list of what an engine could do in general, but what runs through wasmhost on that backend, on that operating system.

Every job of [tests.yml](.github/workflows/tests.yml) runs the suite once per backend, and the suite has one test, `tests/test_feature_probes.py`, that prints one line to the log of the job:
`WASMHOST-SUPPORTS {...}` with the engine and its version, the OS and the Python, the strings of `backend.supports(...)`, whether a WASI 0.1 and a WASI 0.2 program ran, and the answer of every probe
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
| WebAssembly feature | Edition | `wasmtime` (wasmtime-py 49.0.0) | `node` (node 22.23.4, node 24.22.1) | `bun` (bun 1.4.4) | `wasm3` (pywasm3 0.9.1.dev75+g4c1334e03) | `jsc` | `gi-jsc` | `jscontext` | `pyodide` (pyodide 314.0.7) |
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
| `import.global` | yes | yes | yes | not added to wasmhost (pywasm3 links a value; the global is not shared) | yes | yes | yes | yes |
| `import.memory` | yes | yes | yes | no | yes | yes | yes | yes |
| `import.table` | yes | yes | yes | no | yes | yes | yes | yes |
| `imports` | yes | yes | yes | yes | yes | no | yes | yes |
| `isolated` | yes | no | no | yes | no | no | no | no |
| `memory.grow` | yes | yes | yes | no | yes | yes | yes | yes |
| `memory.view` | yes | no | no | yes | no | no | no | no |
| `table.funcs` | yes | yes | yes | no | yes | yes | yes | yes |
| `table.length` | yes | yes | yes | no | yes | yes | yes | yes |
| `table.signatures` | yes | not added to wasmhost (`node --experimental-wasm-type-reflection` gives `.type()`) | no | no | no | no | no | no |
| `threads` | yes | yes | yes | not added to wasmhost (a call from another thread ran in a trial) | no | no | no | no |
| `timeout` | yes | yes | no | yes | no | no | no | no |

| WASI program, run by a host of wasmhost | `wasmtime` | `node` | `bun` | `wasm3` | `jsc` | `gi-jsc` | `jscontext` | `pyodide` |
|---|---|---|---|---|---|---|---|---|
| `wasi_snapshot_preview1` (`Preview1`): arguments, a file in a preopen, `fd_write`, `proc_exit` | yes | yes | yes | yes | yes | no | yes | yes |
| `wasi:*@0.2` (`Preview2`): the probe program, one small component (hello, environment, random, exit) | yes | yes | yes | yes | yes | no | yes | yes |

Measured by CI: 43 different lines of the log, from these combinations:
- `wasmtime`: Darwin, Linux, Windows; CPython 3.10.22, CPython 3.15.1, CPython 3.15.2, PyPy 3.11.17
- `node`: Darwin, Linux, Windows; CPython 3.10.22, CPython 3.15.1, CPython 3.15.2, PyPy 3.11.17
- `bun`: Darwin, Linux; CPython 3.10.22, CPython 3.15.1, CPython 3.15.2, PyPy 3.11.17
- `wasm3`: Darwin, Linux, Windows; CPython 3.15.1, CPython 3.15.2
- `jsc`: Darwin, Linux, Linux (JIT off); CPython 3.10.22, CPython 3.12.3, CPython 3.15.1, CPython 3.15.2, PyPy 3.11.17
- `gi-jsc`: Linux, Linux (JIT off); CPython 3.12.3
- `jscontext`: Darwin; CPython 3.10.22, CPython 3.15.1, CPython 3.15.2
- `pyodide`: Emscripten; CPython 3.14.2
<!-- probe:end -->

## Reading the tables

The notes below are written by hand from the tables and are checked again whenever the tables are written.

From the CI run of `08b9dfe` (Tests run 298, all 14 jobs green, 2026-11-05; the tables did not change from the run of `0cc1a79`, only the list of Node versions: 24.22.2 was not on the runners this time). What the tables say:

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

**`supports(...)`** (run of `08b9dfe`; the same on every OS): host functions (`imports`, and so WASI) are there on every backend but `gi-jsc`, which is why the WASI program ran on seven of the eight; `jscontext` has `imports` once its engine has started. `wasm3` has none of `import.memory`, `import.table`, `table.funcs`, `table.length` and `memory.grow` from Python: pywasm3 can not take a memory or a table from the host (a module that imports a memory loads, but with a memory of its own), has no access to the elements of a table and no growing of a memory from the host (a module's own `memory.grow` works, and `memory.view` sees it). `import.global` is "not added to wasmhost": pywasm3 does link a global **by value** (`link_global`, also a mutable one; checked by hand on 2026-11-05, not in CI), but the object is not shared with the host or with another module, which is what `import.global` means here. **Checked by hand on 2026-11-05 (Node 22.22.0, Bun 1.4.2, pywasm3 as above; not in CI):** a wasm loop `(loop br 0)` is stopped by Node's `vm` timeout (in 331 ms for 300 ms) and is not stopped by Bun's (the process had to be killed), so `timeout` on Bun is an engine limit; `fuel` and `isolated` have nothing in the JavaScript API; `memory.view` on Node and Bun is out of reach because the engine runs in another process; a call into wasm3 from a second Python thread returned its result (one trial, not a stress run). Not run here: the JavaScriptCore engines and Pyodide. What else pywasm3 has and wasmhost does not use: `memory_limit`/`memory_used`, `table_limit`/`table_used`, tags and exceptions, `save_snapshot`/`load_snapshot` and `request_suspend`/`resume`. `table.signatures` is `wasmtime` alone (Node has `.type()` of a function only with `--experimental-wasm-type-reflection`: not added to wasmhost; Bun has none); `timeout` is `wasmtime`, `node` and `wasm3`; `fuel` and `isolated` are `wasmtime` and `wasm3`; `memory.view` is `wasmtime` and `wasm3`; and `threads` (calls from several Python threads) is `wasmtime`, `node` and `bun`.

## WASI

The last two rows of the tables above are measured: one small WASI 0.1 program (`tests/wasm_builder.wasi_hello`: arguments, a file made in a preopen, `fd_write`, `proc_exit`) run by `Preview1`, and one WASI 0.2 program
(`tests/data/wasi2/one.wasm`: hello, environment, random bytes, exit) run by `Preview2`, on each backend. A
backend that can not take host functions (`imports` is "no" in the `supports(...)` table) can not run a WASI program, since a program imports its functions. The rest is what the code and the specification
files in `tests/data/wasi` say (the rows of WASI 0.2 name the commit of their own CI run, which can be later than the run the tables above come from):

| WASI | wasmhost | Notes |
|---|---|---|
| `wasi_snapshot_preview1` (0.1) | yes: all 46 functions, `wasmhost.wasi.preview1.Preview1`, over `fusedwasi` | checked against the specification's witx files; the self-test runs a WASI program on every backend |
| `wasi_unstable` (the first snapshot) | yes: 45 functions (no `sock_accept`) | the same `Preview1` offers both; older toolchains (wasienv, wasm-clang) produce it |
| files | yes: preopens of real folders; `..` and links that leave a folder are `ENOTCAPABLE`; `readonly=` | on POSIX walked with `openat` (fusedwasi reports a stress run with no escape, not a proof); on Windows the check and the open are two steps, so a preopen is not a barrier against another process that can change the folder; links planted by the guest in a folder shared with another process can lead out (see README, "Folders") |
| standard streams, arguments, environment, clocks, random | yes | `thread_cputime_id` reads the process clock on Pyodide |
| sockets in WASI 0.1 | no: `ENOTSOCK` | WASI 0.1 has none to give; use `Preview2` |
| signals | no: `ENOSYS` | `proc_raise` does not end the program here (it does in `wasmext`) |
| `poll_oneoff` that sleeps | yes, but outside what `timeout` and `fuel` can stop | |
| WASI 0.2 of **one component** (`wasi:*@0.2.N`, the core module that `wasm-tools component unbundle` leaves) | yes: `wasmhost.wasi.Preview2`, over `fusedwasi`; CPython for `wasm32-wasip2` (`examples/cpython/run2.py`) runs on it, CI green on `b50b8aa` (wasmtime, Linux x64); by hand on wasm3, Node and Bun, exit code 0 or 1 only; the program of the probe runs on every backend that takes host functions (the second row of the table above) | S0001 step A; `Preview1` and `Preview2` share a `State` (`state=`); the command line is `wasmhost run` with the `-S` flags (`inherit-network`, `allow-ip-name-lookup`, `tcp`, `udp`; `http` too (the next row)); `examples/cpython/run2.py` has the network open by default and ran `pip install` of a wheel from a folder and from a plain-http index by hand on wasmtime (not in CI; no `ssl` in that build) |
| `wasi:http` (outgoing requests) | yes, **denied by default**: `Preview2(http=, http_check=, http_send=)`, `wasmhost run -S http`; fusedwasi's own client (on `h11`) or your `http_send` | step C of S0001; the real-server tests (`tests/test_wasi_http.py`: a local `http.server` on 127.0.0.1:47124 saw `GET /x?q=1`, the guest read status 200; plain http) CI green on `ab99e81`: wasmtime, wasm3, Node, Bun, on Windows (3.15) and on macOS with `jsc` and `jscontext` (JavaScriptCore); Pyodide skips them (no sockets; `h11` comes by micropip), `gi-jsc` has no host functions. Not run: `https`, the guest reading the body; fusedwasi calls `wasi:http` unstable |
| sockets of WASI 0.2 (`wasi:sockets`) | yes, **denied by default**: `network=True` or a `socket_addr_check` opens them | TCP connect shown by the tests on wasmtime, Node, Bun, wasm3 and (macOS) JavaScriptCore; skipped on Pyodide, which has no sockets; UDP, listen and name lookup are not tested |
| WASI 0.2 of **several components** fused by `meld` | yes, through `Preview2(import_map=...)` ([S0004](docs/specs/S0004-wasi-0.2-several-components.md)): CI green on `baef8b8` on wasmtime, wasm3, Node, Bun and Pyodide (two components, each writing to stdout through its own memory); a module of several memories runs on no JavaScriptCore engine; a `--memory shared` fusion of the same two components runs, as one component, on jsc and jscontext (macOS) and jsc (WebKitGTK) | `tests/test_wasi_components.py`; a fusion with `--memory shared` has one memory and one `cabi_realloc` and is run as one component |
| a real component (`.wasm` with the version field `0d 00 01 00`) | no: `Module` refuses it; unbundle or fuse it first | |
| WASI 0.3 (async) | no | out of scope |
| wasi-threads (threads inside the module) | no | not in WASI 0.2 and not in fusedwasi; a shared `Memory` is a `NotImplementedError` |
