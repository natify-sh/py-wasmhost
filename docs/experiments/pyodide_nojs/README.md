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
| wasmtime, wasm3 | can not: the module uses legacy exceptions (`try`), which they do not take (SUPPORTS.md) |

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
