#!/bin/sh
# Builds python2.wasm: the official CPython (python/cpython, branch 3.15, the commit of build.sh) for wasm32-wasip2, with the
# build that CPython itself ships (Platforms/WASI), no patch to its sources, and wasi-sdk 34. The result of the build is a
# component; `wasm-tools component unbundle` takes the one core module out of it (what `Preview2` runs, see
# examples/wasi2/README.md). Needs what build.sh needs, and wasm-tools. The standard library is the one of build.sh
# (lib/python315.zip: the same commit), so there is no second zip.
#   ./build_wasip2.sh     # output: ./python2.wasm
# Sources and the SDK go to $WORK (default ./.build), which is not committed; a checkout of CPython or an SDK that is
# already there is reused only if it has the name that this script makes. Only Linux x86_64 has a checksum of the SDK here.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
work=${WORK:-$here/.build}
cpython_commit=1c6794eb7d0f015c38b2fa7868912c4859f1293c # 3.15.0+dev of 2026-10-20, as build.sh
zlib_commit=51b7f2abdade71cd9bb0e7a373ef2610ec6f9daf # zlib 1.3.1, as build.sh
sdk=34
mkdir -p "$work"

sha256() { if command -v sha256sum > /dev/null; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }

case "$(uname -s)-$(uname -m)" in
	Linux-x86_64) arch=x86_64-linux; want=b761e3a0721dbae9c09a0059e5fdb2bf917d1b4a8a7b430fb3b5aafb0984b2c4 ;;
	*) echo "build_wasip2.sh: the checksum of wasi-sdk $sdk is known for Linux x86_64 only, not for $(uname -s)-$(uname -m)" >&2; exit 1 ;;
esac

if [ ! -d "$work/wasi-sdk-$sdk.0-$arch" ]; then
	curl -fsSL -o "$work/sdk.tgz" "https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-$sdk/wasi-sdk-$sdk.0-$arch.tar.gz"
	[ "$(sha256 "$work/sdk.tgz")" = "$want" ] || { echo "build_wasip2.sh: the checksum of the wasi-sdk is not $want" >&2; exit 1; }
	tar xzf "$work/sdk.tgz" -C "$work"
fi
sdkdir=$work/wasi-sdk-$sdk.0-$arch

src=$work/cpython
if [ ! -d "$src/.git" ]; then
	mkdir -p "$src"
	git -C "$src" init -q
	git -C "$src" remote add origin https://github.com/python/cpython
fi
git -C "$src" fetch -q --depth 1 origin "$cpython_commit"
git -C "$src" checkout -q --detach FETCH_HEAD

zsrc=$work/zlib
if [ ! -d "$zsrc/.git" ]; then
	mkdir -p "$zsrc"
	git -C "$zsrc" init -q
	git -C "$zsrc" remote add origin https://github.com/madler/zlib
fi
git -C "$zsrc" fetch -q --depth 1 origin "$zlib_commit"
git -C "$zsrc" checkout -q --detach FETCH_HEAD
zout=$work/zlib-wasip2
rm -rf "$zout"
mkdir -p "$zout/include" "$zout/lib" "$zout/obj"
for c in adler32 compress crc32 deflate gzclose gzlib gzread gzwrite inflate infback inftrees inffast trees uncompr zutil; do
	"$sdkdir/bin/clang" --target=wasm32-wasip2 -O2 -DHAVE_UNISTD_H -D_LARGEFILE64_SOURCE=1 -c "$zsrc/$c.c" -o "$zout/obj/$c.o"
done
"$sdkdir/bin/llvm-ar" rcs "$zout/lib/libz.a" "$zout"/obj/*.o
cp "$zsrc/zlib.h" "$zsrc/zconf.h" "$zout/include/"

mkdir -p "$work/logs"
# Platforms/WASI builds wasip1 unless it is told the compiler: the three CC, CPP and CXX arguments (with the target) make the
# wasip2 build, and --host-triple names its folder. The zlib arguments are for the WASI build only, as in build.sh.
(cd "$src" && python3 Platforms/WASI build-python --quiet --logdir "$work/logs" &&
	python3 Platforms/WASI build-host --quiet --logdir "$work/logs" --host-triple wasm32-wasip2 --wasi-sdk "$sdkdir" --host-runner true \
		ZLIB_CFLAGS="-I$zout/include" ZLIB_LIBS="-L$zout/lib -lz" \
		CC="$sdkdir/bin/clang --target=wasm32-wasip2" CPP="$sdkdir/bin/clang --target=wasm32-wasip2 -E" CXX="$sdkdir/bin/clang++ --target=wasm32-wasip2")

# the component holds one core module (and the adapters, which a host that runs the module does not need): take the module out and strip it
unb=$work/unbundled
rm -rf "$unb"
mkdir -p "$unb"
wasm-tools component unbundle --threshold 0 --module-dir "$unb" -o "$unb/rest.wasm" "$src/cross-build/wasm32-wasip2/python.wasm"
wasm-tools strip "$unb/unbundled-module0.wasm" -o "$here/python2.wasm"
ls -l "$here/python2.wasm"
