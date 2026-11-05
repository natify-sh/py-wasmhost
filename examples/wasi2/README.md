# WASI 0.2 example files

* `hello.wat`: a core module written by hand in the shape that `wasm-tools component unbundle` leaves of a WASI 0.2
  component: one memory, `cabi_realloc`, imports under `wasi:*@0.2.6` and the export `wasi:cli/run@0.2.6#run`. It prints
  `hello from wasip2`. It also asks for the environment and random bytes (and writes them to its memory), but does not print them.
* `hello.wasm`: `wasm-tools parse hello.wat -o hello.wasm`.

To make a real one: build a component with `clang --target=wasm32-wasip2` (wasi-sdk 34), then
`wasm-tools component unbundle component.wasm` gives the core module that `Module(...)` takes.
See `docs/specs/S0001-wasi-0.2-on-one-state.md`.

The `sock` part of `examples/wasi2.py` uses `tests/data/wasi2/_sock.wasm` (401 KB, not copied here).
