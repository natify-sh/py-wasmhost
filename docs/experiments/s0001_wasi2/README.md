# S0001 prototype: a WASI 0.2 module of one component through wasmhost

Throw-away code for [S0001](../../specs/S0001-wasi-0.2-on-one-state.md), written and run on 2026-11-05 (fusedwasi 0.1.0b1, wasmtime-py 49.0.0, Node 22, Bun 1.4, pywasm3 `4c1334e`). Not part of the package and
not run by CI. It shows that the flat `wasi:*` imports of a core module of one component can be answered by fusedwasi's functions of 0.2 over one `fusedwasi.State`, through wasmhost's own import objects.

| File | What it is |
|---|---|
| `one.wat`, `one.wasm` | a module in the shape `wasm-tools component unbundle` leaves: memory `memory`, `cabi_realloc`, the export `wasi:cli/run@0.2.6#run`, and the imports `get-stdout`, `[method]output-stream.blocking-write-and-flush`, `get-environment`, `get-random-bytes`, `exit` (hand-written WAT; every signature checked with `fusedwasi.signatures.find_import`) |
| `host.py` | the host: class `P2` (`imports(module, comp_of=)`, `bind(instance, mems=, reallocs=)`) and `run(backend)`; prints the exit code, the stdout, the environment read back from memory, the random bytes |
| `two.wat`, `two.wasm`, `two.py` | two memories (`memory`, `memory$1`) and two `cabi_realloc`: shows that `comp` is fixed by the import object, not by the name of the import |
| `dup.wat`, `dup.wasm`, `dup.py` | one module that imports the same `(module, name)` twice: the engine gives one callable to both |

Rerun (from the root of the repository; with fusedwasi 0.1.0b1 installed, after `uv sync`):

```
uv run python docs/experiments/s0001_wasi2/host.py wasmtime node bun wasm3
uv run python docs/experiments/s0001_wasi2/two.py wasmtime wasm3
uv run python docs/experiments/s0001_wasi2/dup.py
```

The `.wasm` files are made from the `.wat` with `wasm-tools parse x.wat -o x.wasm`. Results are in S0001, "Context".
