# S0005: `wasi.for_module`, one call that picks `Preview1` or `Preview2` from the module

Status: approved 2026-11-06 (the owner; the answers to questions 1, 2 and 3 as proposed)
Backlog: B-606 (follow-up of S0001 and S0004)

## Goal
A program that runs a core module with WASI, and does not know before reading it whether the module is of WASI 0.1 or 0.2, writes one call, `wasmhost.wasi.for_module(wasm, **options)`, and gets the right host. It is shown by a test that the same call, with the same
options, runs the 0.1 module and the 0.2 module of `tests/data`, and by `wasmhost run` using this call instead of its own `if`.

## Context
* `wasmhost run` already does this by hand in `src/wasmhost/_run.py`: `wasi_flavor(wasm)`, then `Preview2(**common, **network, import_map=...)` or `Preview1(**common)`. A user who writes their own host repeats it.
* `wasi_flavor` (`src/wasmhost/wasi/_flavor.py`) reads the imports of the bytes: `component`, `core-0.1`, `core-0.2`, `core-0.3`, `none`, `unknown`.
* `Preview1` and `Preview2` already share the part that matters: the options `args`, `env`, `preopens`, `stdin`, `stdout`, `stderr`, `readonly`, and the methods `run(module)`, `instantiate(module, **options)`, `start(instance)`, `bind`, `close`, `with`. They differ in two places:
  `Preview2` has the options `network`, `socket_addr_check`, `allow_ip_name_lookup`, `http`/`http_send`, `import_map`, `memories`, `reallocs`; and `imports()` (`Preview1`) against `imports(module)` (`Preview2`).
* Import graph (read 2026-11-06): `preview2 -> preview1`; `_flavor` imports neither. A new module that imports `_flavor`, `preview1` and `preview2` makes no cycle.
* CLAUDE.md: the API stays close to JavaScript's; no wrapper value types, no second API. So this is a function that returns the existing classes, not a new class. The explicit names `Preview1` and `Preview2` stay.

## The contract
*Proposal, for the owner to approve or change.*
* `wasmhost.wasi.for_module(wasm: bytes | bytearray, **options) -> Preview1 | Preview2`. It reads `wasi_flavor(wasm)` and returns:
  * `core-0.1`, and `none` (a module with no WASI import: same as `Preview1` today for `wasmhost run`): a `Preview1(**options)`;
  * `core-0.2`: a `Preview2(**options)`;
  * `component`: `ValueError`, with the text `wasmhost run` has now (make a core module first: `wasm-tools component unbundle`, or `meld fuse`);
  * `core-0.3`: `ValueError("WASI 0.3 is not supported")`;
  * `unknown` (not a module): `ValueError`.
* An option that only `Preview2` has (`network`, `socket_addr_check`, `allow_ip_name_lookup`, `http`, `http_check`, `http_send`, `import_map`, `memories`, `reallocs`) given for a 0.1 module is a `ValueError` naming the option, never ignored (the rule for `wasmhost run` today: "the network flags are for modules of WASI 0.2").
* The result is used through what the two classes share: `run(module)`, `instantiate`, `start`, `close`, `with`. For `imports` the module is passed: `wasi.imports(module)` works on both (see question 1).
* `wasmhost.wasi` exports `for_module`; its code lives in a new file `src/wasmhost/wasi/_factory.py` (so that `_flavor.py` stays a leaf that imports no host). `wasmhost run` calls it.
* No new `supports(...)` string: it is no engine capability. SUPPORTS.md does not change.

## Matrix
No backend is involved: the function reads bytes and builds a host object. Expected on every backend, as `Preview1` and `Preview2` are.

## Tests and probes
* `tests/test_wasi_factory.py`: a 0.1 module gives `Preview1` and runs; a 0.2 module (`tests/data/wasi2/one.wasm`) gives `Preview2` and runs, on the backend of the run; the errors above (a component, 0.3, not a module, a 0.2 option for a 0.1 module), each with its message.
* `tests/test_cli_run.py` and `tests/test_cli_run2.py` stay as they are and must stay green: the command line behaves as before.
* A self-test step: one 0.1 and one 0.2 module through `for_module` (bytes already in `_selftest.py` and `tests/wasm_builder.py`), asking `supports` first as the other steps do.
* README: a short paragraph with a call. BACKLOG: B-606 notes it.
* CI: Tests and Pre-commit green on every platform; ruff, pyright.

## Out of scope
* A class that holds both versions, or that changes after it is made. No lazy choice of the flavor.
* WASI 0.3, components (no unbundling inside wasmhost), a `Protocol` or a base class for the two hosts.
* Changing `Preview1` or `Preview2` otherwise (except question 1, if the owner says yes).

## Open questions
1. `Preview1.imports()` takes no argument and `Preview2.imports(module)` takes the module. For `for_module(...).imports(module)` to work on both, `Preview1.imports` could take an optional `module` that it ignores (the old call `imports()` keeps working). **Proposed: yes**, one line; otherwise the user of the factory uses `run`/`instantiate` only and the docstring says so.
2. The name: `for_module` (proposed), or `host_for`, `open`, `make`.
3. Should `none` (no WASI import) give `Preview1`, as `wasmhost run` does now? **Proposed: yes**, so that the command line does not change.

## Changes
2026-11-06: `http_check` added to the list of options only `Preview2` has (found while building: `Preview1` has no such argument). `wasmhost run` keeps its own check of `-S` on a 0.1 module (`-S tcp=n` alone gives no option, so the factory would not see it); its `--import-map` check is dropped, the factory's message `` `import_map` is an option of WASI 0.2 `` is shown.
