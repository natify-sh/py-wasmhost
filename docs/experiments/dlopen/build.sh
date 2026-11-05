#!/bin/sh
# Builds the three small programs of the experiment next to this script (wasi-sdk 34 for wasm32-wasip1; WASI_SDK_PATH points at it).
#   WASI_SDK_PATH=/path/to/wasi-sdk-34.0-x86_64-linux ./build.sh
#   WASMHOST_BACKEND=wasmtime python -I run_dl.py main_dl.wasm host     # also node, bun; wasm3 can not (no memory/table imports)
# Two traps found: wasi-sdk 34 makes symbols hidden by default (so -fvisibility=default), and the driver's -shared adds `needed libc.so`
# (so a side module is compiled with -c -fPIC and linked with wasm-ld -shared by hand).
set -eu
cd "$(dirname "$0")"
sdk=${WASI_SDK_PATH:?set WASI_SDK_PATH}
cc="$sdk/bin/clang --target=wasm32-wasip1 -fvisibility=default"
side() { $cc -O1 -c -fPIC "$1.c" -o "$1.o" && "$sdk/bin/wasm-ld" -m wasm32 -shared --export-dynamic --allow-undefined "$1.o" -o "$1.so"; rm -f "$1.o"; }
side side_libc
side side_tbl
side side
# the main module is an ordinary non-PIC program: the table and the stack pointer are exported, the table can grow, and the libc is whole,
# because a side module takes malloc, printf and the like from the main
$cc -O1 main_dl.c -o main_dl.wasm -Wl,--export-table -Wl,--growable-table -Wl,--export-dynamic -Wl,--export=__stack_pointer \
	-Wl,--export-all -Wl,--whole-archive -lc -Wl,--no-whole-archive -Wl,--allow-undefined
ls -l main_dl.wasm side_libc.so side_tbl.so side.so
