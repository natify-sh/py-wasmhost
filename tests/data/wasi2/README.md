# WASI 0.2 test modules (core modules of ONE component)

Used by `tests/test_wasi_preview2.py` and, for `one.wasm`, by the self-test (`WASI2_HELLO` in `src/wasmhost/_selftest.py`, checked equal by `tests/test_selftest.py`).

| File | Where it comes from |
|---|---|
| `one.wat`, `one.wasm` | hand-written in the shape `wasm-tools component unbundle` leaves (copied from `docs/experiments/s0001_wasi2/`); `wasm-tools parse one.wat -o one.wasm`. One memory `memory`, `cabi_realloc`, the export `wasi:cli/run@0.2.6#run` (prints `hello from wasip2\n`, reads the environment to 112, random bytes to 96, returns the result tag at 64) and an export `exit1` that calls `wasi:cli/exit` with 1. |
| `http.wat`, `http.wasm` | hand-written, same shape as `one.wasm`; `wasm-tools parse http.wat -o http.wasm`. Builds a GET to `http://127.0.0.1:9/x?q=1` with `wasi:http/types` and calls `wasi:http/outgoing-handler#handle`; if it is accepted it asks the future for the answer (which sends the request); returns the tag of `handle`'s result (0 ok, 1 err). Used by `tests/test_wasi_http.py`, `tests/test_cli_run2.py`. |
| `_sock.wasm` | wasmext `examples/wasi2_unbundled/c/sock.c` built with wasi-sdk 34 as a component, then `wasm-tools component unbundle` (copied from `examples/wasi2_unbundled/src/wasi2demo/_sock.wasm` of py-wasmext). 401 KB, one memory, 74 imports under `wasi:*@0.2.12`, the export `wasi:cli/run@0.2.12#run`. It connects to 127.0.0.1:47123, sends `ping`, prints `reply: <answer>` and returns 0 from `main`; on an error it prints `perror` text (`connect: Permission denied`) and returns a nonzero code, so `run` gives 1 (`err`). |

## Several components (S0004)

Used by `tests/test_wasi_components.py` and `tests/test_cli_run2.py`. Two small components, A (imports `demo:m/math`, exports `demo:m/app#run`: writes `A-text-ALPHA`, calls `add(40, 2)` of B, writes `A-after-add`) and B (exports `demo:m/math#add`, writes `B-text-BRAVO`); each also calls `wasi:cli/environment get-arguments`. Sources and commands: `docs/experiments/s0004_meld/`. Made with wit-bindgen 0.63.0, wasi-sdk 34 and meld 0.67.0 (the map is schema 2); `demo:m/app@0.1.0#run` returns 42.

| File | What it is |
|---|---|
| `two_multi.wasm`, `two_multi.map.json` | `meld fuse --memory multi`: wasi-libc's allocator, 2 memories (`memory`, `memory$0`), 2 reallocs (`cabi_realloc`, `cabi_realloc$1`), 6 `wasi:*` imports (the second component's with `$2`). 121 KB. Needs `import_map=`. |
| `two_shared.wasm`, `two_shared.map.json` | `meld fuse --memory shared --address-rebase` of the grow-free arena variant: 1 memory, 1 `cabi_realloc`, 3 imports (merged). 38 KB. Runs as one component, no map needed (the map shows `unknown` for `get-arguments`). |
