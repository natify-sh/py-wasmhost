# WASI 0.2 test modules (core modules of ONE component)

Used by `tests/test_wasi_preview2.py` and, for `one.wasm`, by the self-test (`WASI2_HELLO` in `src/wasmhost/_selftest.py`, checked equal by `tests/test_selftest.py`).

| File | Where it comes from |
|---|---|
| `one.wat`, `one.wasm` | hand-written in the shape `wasm-tools component unbundle` leaves (copied from `docs/experiments/s0001_wasi2/`); `wasm-tools parse one.wat -o one.wasm`. One memory `memory`, `cabi_realloc`, the export `wasi:cli/run@0.2.6#run` (prints `hello from wasip2\n`, reads the environment to 112, random bytes to 96, returns the result tag at 64) and an export `exit1` that calls `wasi:cli/exit` with 1. |
| `_sock.wasm` | wasmext `examples/wasi2_unbundled/c/sock.c` built with wasi-sdk 34 as a component, then `wasm-tools component unbundle` (copied from `examples/wasi2_unbundled/src/wasi2demo/_sock.wasm` of py-wasmext). 401 KB, one memory, 74 imports under `wasi:*@0.2.12`, the export `wasi:cli/run@0.2.12#run`. It connects to 127.0.0.1:47123, sends `ping`, prints `reply: <answer>` and returns 0 from `main`; on an error it prints `perror` text (`connect: Permission denied`) and returns a nonzero code, so `run` gives 1 (`err`). |
