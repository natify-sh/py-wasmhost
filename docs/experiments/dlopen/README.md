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
