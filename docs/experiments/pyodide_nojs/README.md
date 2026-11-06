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
* 28 of the 268 function imports are really answered: `environ_*`, `clock_time_get`, `random_get`, `fd_*`, `__syscall_{getcwd,openat,stat64,lstat64,fstat64,newfstatat,readlinkat,faccessat,getdents64,ioctl,fcntl64}`, time and heap calls.
  Everything else (240 imports, among them the bridge to JavaScript, about 130 by name: `Js*`, `Jsv*`, `hiwire_*`, `pyproxy_*`) is a stub that logs and returns 0.
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

## numpy in bare Pyodide, no JavaScript (`run_pyodide_numpy.py`, 2026-11-06)

The question was whether binary wheels are possible without JavaScript at all (the Pyodide issue #558 of 2019-2022 says no: "WASI has no dynamic linking, so packages can not be loaded"). **A wheel of numpy runs**, by hand on Linux with wasmtime-py 50.0.1, not in CI:
Pyodide **315.0.0-alpha.2** (Python 3.15.0rc1, Emscripten 6.0.5; the `pyodide.asm.wasm` of `pyodide-core-315.0.0a2.tar.bz2` and of the npm package are the same files), `numpy-2.4.3-cp315-cp315-pyemscripten_2026_5_wasm32.whl`
(sha256 `aedfd4b129a1a80332d81ff15a432d33103766832f90f90fde0ce8ea1f07bfe2`, from `pyodide-315.0.0a2.tar.bz2`, 35 MB, with 25 wheels). `python run_pyodide_numpy.py PYODIDE_DIR SITE_DIR "$(cat numpy_check.py)"` printed, in about 12 to 16 s (start, import, the work):

```
python 3.15.0rc1 numpy 2.4.3
sum 499999500000.0 mean 499999.5 std 288675.135          # std is sqrt((N^2-1)/12) for N = 1e6, by hand: 288675.1346
matmul [[14, 38, 62], [38, 126, 214], [62, 214, 366]]
linalg inv [[0.6, -0.2], [-0.2, 0.4]]                    # the analytic inverse
fft [28.0, 10.453, 5.657, 4.33, 4.0, ...]                # |X0| = 28, |X1| = sqrt(16 + 9.657^2) = 10.453
random [8, 77, 65, 43, 43] 0.697368                      # default_rng(42).integers(0, 100, 5), the well-known sequence
lstsq [0.6667, 0.5]                                      # the line through (1,1), (2,2), (3,2)
```

All 13 extension modules of numpy (`_multiarray_umath`, `_umath_linalg`, `_pocketfft_umath`, the random generators, ...) were loaded with no unresolved import: every name is a symbol of the main module (`pyodide.asm.wasm` exports 8 558 names, among them the exception tag `__cpp_exception`), of another numpy module, or of the loader.

**What the host does that the JavaScript glue did** (about 300 lines on top of `run_pyodide_wasmtime.py`; the glue's `loadWebAssemblyModule`, lines 741-905 of the formatted `pyodide.asm.mjs`, is the model): `_dlopen_js` reads the `dylink.0` section, takes memory from the main module's `calloc`, grows the table,
instantiates the side module with the main module's memory, table, stack pointer and exception tag, resolves `GOT.mem` / `GOT.func` (a name of the main module, of a module loaded before, or the module's own: patched after instantiation; its own functions are called through a trampoline), then runs `__wasm_apply_data_relocs` and `__wasm_call_ctors`;
`_dlsym_js` gives a table slot for a function and `base + value` for a data symbol; `ffi_closure_alloc_js` is what `import ctypes` needs (numpy imports it); the file calls grew by `getdents64` (a listing of a directory: the first version kept the position by descriptor number and an old position made a new directory look empty).

**The wheel has to be prepared:** `_multiarray_umath` and `_pocketfft_umath` use the old exception handling (162 and 265 `try`/`catch`), so, like the main module, they go through `wasm-opt --all-features --disable-compact-imports --translate-to-exnref` (Binaryen 132, npm). The other 11 need nothing.

**What this does not show.** (1) The loading is done by the host (our Python code), not by the module: on a WASI host with no loader, wheels do not load. (2) One Pyodide build and one package. Not tried: scipy (Fortran, BLAS), threads, a C++ exception that is really thrown (the tag is shared, nothing threw), callbacks of `ctypes` (`ffi_prep_closure_loc_js` is still a stub), the network, writing files (bytecode caches are off: `PYTHONDONTWRITEBYTECODE`), the other engines (wasmhost's own wasmtime backend can not run Pyodide: `externref` in a host function), the iPhone.
(3) The conversion of the exceptions is Binaryen's and was not proved correct. (4) The same numpy **also runs on our own CPython for wasm** (`wasm32-wasip1`, relinked; see `docs/experiments/dlopen/README.md`, "numpy on our own CPython"): there the main module had to be given 283 names that Pyodide's main module has (libc, libm, long double, a small C++ runtime).
