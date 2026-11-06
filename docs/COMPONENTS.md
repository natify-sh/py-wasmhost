# Running a WebAssembly component with wasmhost

wasmhost runs **core modules**, not components. A WASI 0.2 program is usually built as a *component* (a wrapper around core modules and a description of its interfaces); the engines that wasmhost drives
(wasmtime-py, Node, Bun, wasm3, JavaScriptCore) take core modules, so the component has to be turned into one first. This page shows how, from what was run (2026-11-05, Linux, `wasm-tools` 1.262.0, `meld` 0.67.0,
the default backend `wasmtime` unless another is named). The design is in [S0001](specs/S0001-wasi-0.2-on-one-state.md), [S0003](specs/S0003-several-memories.md) and [S0004](specs/S0004-wasi-0.2-several-components.md).

## 1. Get the tools
Both are on PyPI: `wasm-tools-package` (the command `wasm-tools`) and `meld-cli` (the command `meld`; only for several components; installed here with `uv tool install meld-cli`). The wheels are small, but
`files.pythonhosted.org` can be slow in a sandbox. A component itself comes from a compiler: `clang --target=wasm32-wasip2` (wasi-sdk 34) makes one; `wit-bindgen` makes the glue for your own interfaces (recipe: `docs/experiments/s0004_meld/`).

## 2. One component: take the core module out
```shell
wasm-tools component unbundle --threshold 0 --module-dir mods -o rest.wasm component.wasm
```
`unbundle` moves the core modules of the component into `--module-dir` (as `unbundled-module0.wasm`, ...) and writes a new component (`-o`) that imports them. `--threshold 0` takes **every** module out; the default
leaves the small ones inside the component. Run on a tiny hand-written component (184 bytes, one module, no WASI) it left `mods/unbundled-module0.wasm`, 61 bytes, and a 186-byte `rest.wasm`. For a real program (CPython built for `wasm32-wasip2`)
the module is the big file: `examples/cpython/build_wasip2.sh` does exactly this and runs `Preview2` on `unbundled-module0.wasm`.

`Preview2` wants the shape that this leaves: one memory exported as `memory`, an export `cabi_realloc`, the export `wasi:cli/run@0.2.N#run`, and flat imports under `wasi:*@0.2.N`.

## 3. Run it
```shell
wasmhost run examples/wasi2/hello.wasm        # prints "hello from wasip2", exit 0 (run on wasmtime, node, wasm3 and bun: the same)
```
In Python:
```python
from wasmhost import Module
from wasmhost.wasi import Preview2

code = Preview2(env={"A": "1"}, stdout=out.append).run(
    Module(open("prog.wasm", "rb").read())
)  # 0 ok, 1 err, or the code of wasi:cli/exit
```
Options (the same as `Preview1`): `args`, `env`, `preopens`, `stdin`, `stdout`, `stderr`, `readonly`; on the command line `--dir`, `--env`, `-S`. The exit code of `wasi:cli/run#run` is only ok or err: a program that calls `exit(3)` gives 1.

**The network is denied by default** (`network=True` or `-S inherit-network` opens it; `-S` takes wasmtime's flags: `inherit-network`, `allow-ip-name-lookup`, `tcp`, `udp`, `http`). Full description: README, "WASI 0.2".

## 4. Several components fused by `meld`
Two components (here A calls B's `add`) become one core module with `meld`:
```shell
meld fuse a.wasm b.wasm --memory multi --emit-import-map fused.map.json -o fused.wasm
```
`--memory multi` keeps a memory and a `cabi_realloc` for each component (`memory`, `memory$0`, `cabi_realloc`, `cabi_realloc$1`: the names differ between `meld` versions, so read them with
`wasm-tools print fused.wasm | grep -E 'export "(memory|cabi_realloc)'`). The map says which memory each `wasi:*` import uses. Run it (the files are in `tests/data/wasi2/`; this module exports no
`wasi:cli/run`, so `--invoke` names the export; the program writes three lines and the function returns 42):
```shell
wasmhost run --import-map tests/data/wasi2/two_multi.map.json --invoke 'demo:m/app@0.1.0#run' tests/data/wasi2/two_multi.wasm
```
```
A-text-ALPHA 1 two_multi.wasm
B-text-BRAVO 1 two_multi.wasm
A-after-add 1 two_multi.wasm
42
```
Same output, exit 0, on wasmtime, Node, wasm3 and Bun. In Python: `Preview2(import_map="fused.map.json").instantiate(Module(data))`, then a call of the export.

`--memory shared --address-rebase` gives one memory and one `cabi_realloc`: it needs no map and runs as one component (`two_shared.wasm`, the same four lines, exit 0, on the same four backends). The catch: `meld`
refuses `memory.grow` under address rebasing, so the programs have to use an allocator that never grows (`docs/experiments/s0004_meld/arena.h`).

## 5. What works where
See [SUPPORTS.md](../SUPPORTS.md) (it is made from CI; not copied here). In short: one component runs on every backend that takes host functions. A module with **several memories** (`--memory multi`) is refused by the
JavaScriptCore engines (S0003); the shared fusion runs on them as one component. `gi-jsc` has no host functions, so no WASI at all. Not supported: WASI 0.3. The JavaScriptCore engines were not available in the session
that wrote this page, so their lines are from CI, not from the commands above.

## 6. Errors you will meet
* `Error: the module exports several cabi_realloc (it was fused from several components): give import_map=, made by 'meld fuse --emit-import-map', or fuse one component`: a `--memory multi` module run without `--import-map`.
* `Error: the module exports no wasi:cli/run@0.2.N#run`: the module is not a command (it has your own export): name it with `--invoke`.
* A real component given to `Module`: refused; unbundle it (section 2).
* `ValueError` about the map: its `version` is not 2 (`meld` 0.65 or later writes 2).
* A `wasi:` import that fusedwasi has no function for (for example WASI 0.3) is a `LinkError`.
