# S0004: two components fused by meld

The sources of the modules in `tests/data/wasi2/two_*.wasm`. A (`a_impl.c`) and B (`b_impl.c`) are two WASI 0.2 components; `common.h` has the function `say` that both use (it calls `wasi:cli/environment get-arguments`, then writes a line to stdout with `wasi:io/streams`). `wit/world.wit` has the worlds `a` and `b`; `wit/deps` are the WASI 0.2.12 interfaces.

Tools: wit-bindgen 0.63.0, wasi-sdk 34 (clang 23.1.0), meld 0.67.0. The commands below were put together afterwards from the files (they were not re-run in this exact form) and from the attestation meld wrote into the output; the first (meld) step was repeated here with a meld 0.64 binary, which gives other bytes, so the committed bytes are the ones the 0.67.0 run left.

```
# bindings (one directory for each component)
wit-bindgen c --world a wit --out-dir ga
wit-bindgen c --world b wit --out-dir gb

# the multi variant: the default allocator of wasi-libc
SDK=wasi-sdk-34.0-x86_64-linux
$SDK/bin/clang --target=wasm32-wasip2 -O2 -Wl,--emit-relocs a_impl.c ga/a.c ga/a_component_type.o -o a.wasm
$SDK/bin/clang --target=wasm32-wasip2 -O2 -Wl,--emit-relocs b_impl.c gb/b.c gb/b_component_type.o -o b.wasm
meld fuse a.wasm b.wasm --memory multi --emit-import-map two_multi.map.json -o two_multi.wasm

# the shared variant: the same with a_ng.c / b_ng.c (they include arena.h), then
meld fuse a_ng.wasm b_ng.wasm --memory shared --address-rebase --emit-import-map two_shared.map.json -o two_shared.wasm
```

`-Wl,--emit-relocs` is what meld needs to rebase addresses. **The arena variant** (`arena.h`) replaces the allocator by a static bump arena (`cabi_realloc` of its own, a no-op `free`) because meld refuses `memory.grow` under address rebasing and wasi-libc's `malloc` grows memory; `--memory shared` without rebasing is refused too (overlapping data segments). So the shared module is a build of a program with a grow-free allocator, not of a general one, and it is the one-component shape for the host (one memory, one `cabi_realloc`, the imports of the two components merged).

What was measured with them (2026-11-05, see S0004 "Context"): multi gives 2 memories and a complete map; a host that routes every import to one component prints corrupt output (the test `test_every_import_routed_to_component_zero_is_corrupt`); shared runs correctly with this allocator only.
