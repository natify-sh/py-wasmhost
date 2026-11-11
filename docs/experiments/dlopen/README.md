# dlopen on WASI: wasmhost as the dynamic loader (an experiment, 2026-11-05)

The question (the owner's): CPython built for WASI (`examples/cpython/python.wasm`, `python2.wasm`) can not load a wheel with compiled code, as WASI has no `dlopen`,
while Pyodide (`wasm32-emscripten`) can. Could wasmhost, as the host, load a side module the way Emscripten's JavaScript does? Pyodide does it with Emscripten's own
`dlopen` and a JS loader; the convention is [DynamicLinking.md](https://github.com/WebAssembly/tool-conventions/blob/main/DynamicLinking.md).

**Answer of the experiment: yes, at the wasm level, with about 160 lines of Python on the public API of wasmhost, on `wasmtime`, `node` and `bun`; `wasm3` can not.**
Nothing here is CPython yet.

## What is here
- `dl_loader.py`: the loader. It reads the `dylink.0` section of a side module, takes `__memory_base` from the main module's own `aligned_alloc` and `__table_base` from
  `table.grow`, builds the `GOT.mem` and `GOT.func` globals from the main's exports, instantiates the side module on the **same `Memory` and `Table`** as the main, shares
  `__stack_pointer`, patches the module's own symbols, calls `__wasm_apply_data_relocs` and `__wasm_call_ctors`, and answers `dlopen`/`dlsym`.
- `main_dl.c` (calls the real `dlopen`/`dlsym`/`dlerror`, bound to host imports `env.dlopen` and so on instead of the stubs of `libdl.a`), `side_libc.c` (the side module
  uses `malloc`, `strcpy`, `printf` of the main), `side.c` (a data relocation, a call back into the main through `GOT.func`/`GOT.mem`, a constructor, the shared stack),
  `main.c`, `main_tbl.c` and `side_tbl.c` (a `PyMethodDef`-like table: strings and pointers to the module's own functions), `run_dl.py` (the runner), `build.sh`.
- Build and run (wasi-sdk 34): `WASI_SDK_PATH=... ./build.sh`, then `WASMHOST_BACKEND=wasmtime python -I run_dl.py main_dl.wasm host`; the output is
  `side printf: hello via real dlopen (21)` and exit 0. The built files are not committed (`main_dl.wasm` is 2 MB: the whole libc is linked in).

## Measured (by the agent that made it; the run of `main_dl` on wasmtime, node, bun re-run by the orchestrator from this folder)
- `clang --target=wasm32-wasip1 -fPIC` and `wasm-ld -shared` make a side module with a `dylink.0` section. Two traps: wasi-sdk 34 makes symbols hidden by default
  (`-fvisibility=default`), and the clang driver's `-shared` adds `needed libc.so` (link with `wasm-ld -m wasm32 -shared --export-dynamic --allow-undefined` by hand).
- **The main module does not have to be PIC**: a plain non-PIC program with the table and the stack pointer exported (`--export-table --growable-table
  --export=__stack_pointer`), `malloc`/`aligned_alloc` and the libc exported (`--export-all` with the whole libc linked in) is enough. So no speed cost for the interpreter.
- wasi-libc has no `dlopen` (`libdl.a` has weak stubs that fail with "dlopen not implemented"; `libdl.so` imports `env.dlopen` etc., which a loader provides).
  The existing `python.wasm` already has `dynload_shlib.c` compiled in and reaches that stub: `import foo` on a `foo.cpython-315-wasm32-wasi.so` gives
  `ImportError: dlopen not implemented` (run once by the agent).
- Backends: `wasmtime`, `node`, `bun` take `Memory`, `Table` and `Global` as imports and run it identically. **`wasm3` can not** (`pywasm3 has no tables API`; `supports("import.memory")` is false):
  it fails at the first step. `jsc`, `jscontext`, `pyodide` say `import.*` is yes in README, but were **not run** here (no JavaScriptCore library on this machine); `gi-jsc` has no host functions.
- `python.wasm` and `python2.wasm` as they are can not be used: they export no table (the table is internal and fixed), no allocator in `python.wasm`. They need a relink.

## Not done, and what it would cost (the agent's estimates, not measurements)
- Relink CPython as the main module with the export flags above (its C API is about 1800 functions and 240 data symbols; the stable ABI 824 and 143): about a day in the build scripts.
- CPython's own side: the tree at commit 1c6794e already has `--enable-wasm-dynamic-linking` for WASI and `dynload_shlib.c` (no change of C code expected, not tested); `LDSHARED` for WASI says
  `not implemented yet` in `configure.ac`. 1 to 3 days, medium risk (the real link was not run).
- A loader in wasmhost (a new module, not a method of `Instance`; files read through the same preopens the program sees, which the prototype does not do; `needed` libraries, `dlclose`, `dlerror`
  text, `RTLD_GLOBAL` missing in the prototype): 1 to 2 days with tests and a self-test step; **it needs a spec first** (CLAUDE.md).
- Packaging: no standard wheel tag for WASI exists (Pyodide has PEP 783 `pyodide_YEAR_wasm32`); pip inside the guest would not choose such a wheel; the first realistic target is our own small C extensions,
  not numpy (libm, C++, threads, BLAS).
- A real WASI 0.2 **component** keeps its memory private, so a side module can not be given it; only the unbundled core module run through `Preview2` can (inference, not tested).
- Not verified: any real CPython extension, the relinked CPython, jsc/jscontext/pyodide, Windows/macOS, wasm3 at the C level, sandboxing of the loader.

## CPython 3.15 with dlopen (`python3.wasm`) and Emscripten wheels (2026-11-05, measured by hand, wasmtime and node; not in CI)

Files: `dl_loader_cpy.py` + `run_cpy_dl.py` (loader and driver on the public API), `foo.c` (a tiny extension),
`t_emscripten_*.py` (guest scripts).

Relink of the CPython objects (7 s, no rebuild): take the captured link line of `python.wasm` and apply
`sed 's| -ldl | |; s| -o python.wasm | -Wl,--skip-wit-component -Wl,--export-table -Wl,--growable-table -Wl,--export=__stack_pointer -Wl,--export-dynamic -Wl,--allow-undefined -Wl,--export=memcmp -Wl,--export=strlen -Wl,--export=strcmp -Wl,--export=strrchr -Wl,--export=ntohs -Wl,--export=ntohl -o python3.wasm |'`.
The result is a core module (not a component) that imports `env.dlopen/dlsym/dlerror` and exports its table, stack pointer and the whole C API.

Results:
* `foo.cpython-315-wasm32-wasi.so` (built with wasi-sdk): `import foo` works on wasmtime, node, bun.
* `python3.wasm` with OpenSSL 3.5.0: `import ssl` works on wasmtime and node; bun dies (status -11) with the 36 MB module (not investigated).
* **Emscripten wheels work as they are** (`msgpack` cp315 `pyemscripten_2026_5_wasm32` from PyPI): the `.so` has the same
  `dylink.0` convention as ours and imports only the C API of Python plus a few libc functions; no `__syscall_*`, `emscripten_*` or `invoke_*`.
  `msgpack._cmsgpack` packs and unpacks. The only changes: the file suffix `.cpython-315-wasm32-emscripten.so` has to be added to the extension
  finder (`t_emscripten_msgpack.py`), and the main must export the libc functions the wheel imports (list them with `wasm-tools print`).
* `bitarray` cp315 Emscripten wheel: import, `bitarray("1011")`, `extend`, `count` work; `tolist()` traps with `indirect call type mismatch`
  in `cfunction_vectorcall_NOARGS`. **Confirmed cause** (read from the `.so`): the `PyMethodDef` of `tolist` has `flags=4` (`METH_NOARGS`, which CPython calls as
  `f(self, NULL)`), but table slot 57 holds a function of type `(i32) -> i32`: the C function is declared with one argument and cast. A wasm `call_indirect`
  checks the type and traps. Emscripten CPython hides this with `Python/emscripten_trampoline.c` (`PY_CALL_TRAMPOLINE`, compiled only under
  `__EMSCRIPTEN__`): it calls the function from JavaScript, `wasmTable.get(func)(a, b, c)`, and JS does not check arity. WASI CPython has no such path.
  A fix needs a trampoline on our side, for example a host import `env.py_tramp(func, a1, a2, a3)` in a patched `methodobject.c`, with the host calling the table entry with its own arity.
* `contourpy` (C++, pybind11) imports about 300 C++ runtime symbols (libc++, libc++abi, `_Unwind_CallPersonality`, `__wasm_lpad_context`): the main would need libc++ and wasm exception handling. Not tried.
* numpy/scipy/pillow have no Emscripten wheel on PyPI (pandas cp312, pydantic-core cp314 only); the Pyodide CDN is not reachable from the sandbox, so numpy was not tried.

### py-ballisticcalc-exts (C++ + Cython, Emscripten wheel from PyPI) - works

`py_ballisticcalc_exts-3.1.1-cp315-cp315-pyemscripten_2026_5_wasm32.whl` (six C++/Cython `.so`) plus the pure-Python
`py_ballisticcalc` run on `python3.wasm` (wasmtime and node): the Cython RK4 engine and the pure-Python RK4 engine
give the same trajectory (1000 yd: height -401.634 in, velocity 1079.64 fps). Script: `t_emscripten_ballisticcalc.py`.

What the main module and the loader had to supply (found by listing the imports of the six `.so` with `wasm-tools print`):
* `cxx_shim.c`: the ten libc++ symbols the wheel imports (`operator new/delete`, `std::recursive_mutex`, `std::sort` of doubles, `nothrow`,
  `__cxa_pure_virtual`), written in C and linked into the main. No libc++ and no exception support needed: the wheel throws nothing.
  Trap met on the way: on wasm the C++ ABI makes constructors and destructors **return `this`**; a shim that returned nothing gave
  "host function should return 1 value" inside the module.
* libm (`sin cos tan atan2 exp pow fmin fmax`), `strlen`, `abort`: exported from the main with `-Wl,--export=`.
* Loader: a module's own default-visibility functions are imports too (`env.<own symbol>`; called through a trampoline because the instance does not
  exist yet), and symbols of libraries loaded earlier (`bind`, `base_engine`, ... share C++ classes) are looked up in them (`dl_loader_cpy.py`:
  `resolve_func`, `sibling_sym`).
Not needed: libc++ itself. It would be for C++ code that throws (`contourpy` does, via pybind11).

## The same on wasmtime-py alone (`wasmtime_only.py`)

No wasmhost, no fusedwasi, no JavaScript: `pip install wasmtime`, `WASI_SDK_PATH=... ./build.sh`, `python wasmtime_only.py`. WASI is wasmtime's own (`Linker.define_wasi`,
preview1); the loader (about 100 lines) is the same one as in `dl_loader.py`, written on the wasmtime-py API (a `Linker` per side module, the memory, table and stack
pointer of the program defined into it). Result (wasmtime-py 49.0.0, Linux): `dlopen("side_libc.so")` gives memory base 275008 and `side_libc` calls the program's `printf`: `side printf: hello via real dlopen (21)`, exit code 0.
What it can **not** do: the CPython of `python3.wasm` is a WASI 0.2 module (`wasi:*@0.2` imports), and wasmtime-py has no host for those on a core module: that part is what wasmhost's `Preview2` over fusedwasi gives.
And `pyodide.asm.wasm` does not load on wasmtime (legacy exceptions).

### numpy on our own CPython for wasm, on wasmtime-py alone (`run_cpython_numpy.py`, 2026-11-06)

numpy 2.4.3 (the wheel `numpy-2.4.3-cp315-cp315-pyemscripten_2026_5_wasm32.whl` of Pyodide 315.0.0a2, built for Emscripten) runs on **our** CPython 3.15.0+dev for `wasm32-wasip1` (`examples/cpython/build.sh`, the commit it names), with wasmtime's own WASI and the loader in Python:
`python run_cpython_numpy.py python.wasm SITE_DIR` gives the same answers as in Pyodide (`numpy 2.4.3 45`; the whole `docs/experiments/dlopen/numpy_check.py`: sum, mean, std, matmul, inv, sort, fft, `default_rng(42)`, lstsq), in 4 to 5 s with wasmtime-py 50.0.1. By hand, not in CI. The 13 extension modules load; no JavaScript.

What it took, and what was found on the way (the wheel is made for Pyodide's runtime, not for ours, so each of these is something the main module had to give):
* **A relink, 7 s** (`relink_numpy.sh`: the link line of the CPython build with the table and every symbol exported). numpy's modules import 283 names that the `python.wasm` did not export: 224 of libc, libm and the compiler-rt of long double (forced with `-u` and `--export-if-defined`; 220 exist, `__fpclassifyl`, `__signbitl`, `fiprintf` and the data `__wasm_lpad_context` are answered by the loader), and 29 of the C++ runtime.
* **`strtold`**: wasi-libc's `strtold` aborts (`long_double_not_supported`) and `_multiarray_umath` calls it while it starts; linking `-lc-printscan-long-double` fixes it.
* **`operator new` is really called** at start-up (`_Znwm`), so the C++ runtime is not only for exceptions: `cxx_shim_np.c` has real `new`/`delete`, a `__next_prime` and a `__hash_memory` for libc++'s containers, and stubs for the exception functions (nothing threw on the paths that were run). The exception tag `__cpp_exception` is a new tag that the loader makes and shares between the modules.
* **Two modules (`_multiarray_umath`, `_pocketfft_umath`) have the old exception handling**, so they were converted with Binaryen as for Pyodide.
* The wheel's file suffix is `.cpython-315-wasm32-emscripten.so`: a path hook adds it (as for msgpack). The wheel is for Python 3.15.0rc1 and ours is 3.15.0+dev of 2026-10-20; nothing broke, but that is no promise for the whole C API.

Not tried: scipy, threads, a C++ exception that is really thrown (they are stubs: it would abort), the other engines, wasmhost (its API has no tags, so the two modules that import the exception tag can not be loaded through it), the network.
