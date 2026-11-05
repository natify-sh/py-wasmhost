# Pyodide's `pyodide.asm.wasm` without Pyodide's JavaScript (experiment, 2026-11-05)

Not a goal and not part of wasmhost: an experiment of what is possible, by hand, **not in CI**. Linux, Node 22.22.0 as the WebAssembly engine, pyodide 314.0.7 (Python 3.14.2, npm package).

```
WASMHOST_BACKEND=node python run_pyodide_nojs.py PYODIDE_DIR ["python code"]
```

`PYODIDE_DIR` holds `pyodide.asm.wasm` and `python_stdlib.zip`. Needs `wasm-tools` on PATH.

## What it shows
`pyodide.asm.wasm` is an Emscripten main module with 548 imports: 254 `env` functions, 14 `wasi_snapshot_preview1` functions and 280 `GOT.func` globals. Here a Python host answers them and the
engine (Node) only runs the WebAssembly: `Py_Initialize`, then `PyRun_SimpleString`.

| Run | Result |
| --- | --- |
| `print(sys.version)`, `sum(range(10))` | 3.14.2, `45` |
| `import json, collections, platform, hashlib, zlib` (from `python_stdlib.zip` through the file calls of the host) | right answers, `sys.platform` is `emscripten` |
| a list of 2 000 000 squares | works (the host grows the memory: `emscripten_resize_heap`) |
| Bun | `BrokenPipeError` (the process died; not investigated) |
| wasmtime, wasm3 (the file as shipped) | can not: the module uses legacy exceptions (`try`), which they do not take (SUPPORTS.md); see below for wasmtime |

## What the host had to do
* The 280 `GOT.func` globals are filled by hand with table slots of the module's own functions (what the Emscripten loader does).
* `_PyEM_TrampolineCall_JS(func, a, b, c)` is what `wasmTable.get(func)(a, b, c)` is in JavaScript: a call that drops extra arguments and fills missing ones. The host reads the
  type of the table entry from the module (`wasm-tools print`) and calls with that many arguments. The same thing is what `bitarray.tolist` needs in `docs/experiments/dlopen`.
* About 20 calls are really answered: `environ_*`, `clock_time_get`, `random_get`, `fd_*`, `__syscall_{getcwd,openat,stat64,lstat64,fstat64,newfstatat,readlinkat,faccessat,getdents64,ioctl,fcntl64}`, time and heap calls.
  Everything else (about 230 imports, among them the whole bridge to JavaScript: `Js*`, `hiwire_*`, `pyproxy_*`) is a stub that logs and returns 0.
* The files are a temporary folder with `lib/python314.zip`; no sandbox (a path is only joined to the root).

## Not done
* No JavaScript objects: `pyodide.ffi`, `js`, promises and `micropip` need the bridge. Loading a package (`dlopen`) is not done either.
* The 14 WASI calls are written by hand here; `Preview1` over fusedwasi provides all 14 (names checked, not run), but the `__syscall_*` would have to go through its file state too.

## Pyodide on wasmtime-py alone (`run_pyodide_wasmtime.py`, 2026-11-05)

The owner's question: can it run on wasmtime, with no JavaScript and none of our libraries? **Yes, after one offline conversion.** wasmtime refuses the module as shipped
(`legacy_exceptions feature required for try instruction`). Binaryen 132 (the npm package `binaryen`, used only as a tool, not at run time) rewrites the legacy
exceptions to the new `exnref` ones: `wasm-opt pyodide.asm.wasm --all-features --disable-compact-imports --translate-to-exnref` (8 s; without `--disable-compact-imports` wasmtime 49
can not read the output: `invalid leading byte 0x7E with compact imports proposal disabled`). The converted file compiles on wasmtime-py 49.0.0 with `Config.wasm_exceptions = True`.

`python run_pyodide_wasmtime.py PYODIDE_DIR "code"` needs only `pip install wasmtime`. Result (Linux): `sys.version` is 3.14.2, `json`, `hashlib`, `zlib`, `decimal`, `fractions` from the stdlib zip,
2 000 000 squares in a list, a caught `ZeroDivisionError`; a run takes about 8 s with the start. Differences from the Node script: no wasmhost (its wasmtime backend can not make a host function
with an `externref` parameter, which the stubs of the JavaScript bridge need), the type of a table entry for the trampoline comes from `Func.type()`, not from `wasm-tools`.

Not verified: that the conversion keeps the semantics of every exception path (only the paths that these programs use ran; C++ exceptions that the bridge would throw were not exercised, because the bridge is stubbed); the conversion is
Binaryen's, not ours. Not done: the bridge to JavaScript, `dlopen` and packages, sockets, any CI.

## One file, `uv run` (`pyodide_repl.py`)

`uv run docs/experiments/pyodide_nojs/pyodide_repl.py` (or `-c "code"`): a PEP 723 script whose only dependency is `wasmtime`. It downloads the npm package `pyodide` 314.0.7
(checked against the integrity hash of the registry), converts `pyodide.asm.wasm` once and starts `code.interact` in it. The conversion needs Binaryen's `wasm-opt` (130 or newer)
on PATH, or named by `--wasm-opt` / `$WASM_OPT`: the script downloads no program (`brew install binaryen`, or `npm install -g binaryen`; in this session the npm one, run by Node, made the
converted file). Why it is needed: wasmtime does not take the legacy exceptions of the shipped module, and the conversion rewrites them to `exnref` ones. By hand on Linux, from an empty cache: about 1 minute
(download, conversion), later starts a few seconds; the REPL ran expressions, `print`, `json`, a traceback of `ZeroDivisionError` and a multi-line loop (input through a pipe; a real terminal was not tried).
Not tried: Windows, macOS, an installed `wasm-opt` of another version than the npm 132.
