#!/bin/sh
# Relinks the CPython of examples/cpython/build.sh (wasm32-wasip1) so that numpy's Emscripten wheel can load into it (7 s, no rebuild).
#   WASI_SDK_PATH=... ./relink_numpy.sh LINK_LINE.sh CROSS_BUILD_DIR OUT.wasm
# LINK_LINE.sh: the line of `-o python.wasm` from the log of the build (`$WORK/logs/cpython-wasi-*.log`, the one that has `-o python.wasm`);
# CROSS_BUILD_DIR: `$WORK/cpython/cross-build/wasm32-wasip1`. What it changes, by hand, with the flags that were found to be needed:
#   * no `-ldl`, so that dlopen/dlsym/dlerror are imports of the host; the table, the stack pointer and every symbol are exported;
#   * `-u` and `--export-if-defined` for each name of numpy_libc_names.txt (libc, libm and the compiler-rt of long double that the wheel imports);
#   * `-lc-printscan-long-double`: without it `strtold` aborts and importing numpy dies at its first long double constant;
#   * cxx_shim_np.c: operator new/delete and the few helpers of libc++, exception functions as stubs.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
line=$1; cross=$2; out=$(cd "$(dirname "$3")" && pwd)/$(basename "$3")
sdk=${WASI_SDK_PATH:?set WASI_SDK_PATH}
"$sdk/bin/clang" --target=wasm32-wasip1 -O2 -c "$here/cxx_shim_np.c" -o "$out.shim.o"
force=""
for n in $(cat "$here/numpy_libc_names.txt"); do force="$force -Wl,-u,$n -Wl,--export-if-defined=$n"; done
exports="-Wl,--export=__cxa_atexit"
for n in $(grep -o -E '^(void|size_t|int|char)[ *]+\**[A-Za-z_0-9]+|, *_[A-Za-z0-9_]+\[' "$here/cxx_shim_np.c" | sed -E 's/^(void|size_t|int|char)[ *]+//; s/^, *//; s/\[//' | sort -u); do exports="$exports -Wl,--export=$n"; done
sed "s| -ldl | |; s| -lm | -lc-printscan-long-double -lm |; s| -o python.wasm | -Wl,--export-table -Wl,--growable-table -Wl,--export=__stack_pointer -Wl,--export-dynamic -Wl,--allow-undefined $force $exports $out.shim.o -o $out |" "$line" > "$out.link.sh"
(cd "$cross" && sh "$out.link.sh")
rm -f "$out.shim.o" "$out.link.sh"
ls -l "$out"
