#!/bin/sh
# Builds python2_ssl.wasm: the official CPython (python/cpython, branch 3.15, the commit of build.sh) for wasm32-wasip2 WITH OpenSSL
# (`_ssl` and `_hashlib`), with the build that CPython itself ships (Platforms/WASI), no patch to its sources, and wasi-sdk 34.
# OpenSSL 3.5.0 is built first for wasm32-wasip2 (static libssl.a and libcrypto.a, see the flags below), then CPython is
# configured with --with-openssl. The result is a component; `wasm-tools component unbundle` takes the one core module out of it
# (what `Preview2` runs). Needs what build_wasip2.sh needs, plus perl (OpenSSL's Configure) and make.
#   ./build_wasip2_ssl.sh     # output: ./python2_ssl.wasm
# Sources and the SDK go to $WORK (default ./.build), which is not committed. Only Linux x86_64 has a checksum of the SDK here.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
work=${WORK:-$here/.build}
cpython_commit=1c6794eb7d0f015c38b2fa7868912c4859f1293c # 3.15.0+dev of 2026-10-20, as build.sh
zlib_commit=51b7f2abdade71cd9bb0e7a373ef2610ec6f9daf # zlib 1.3.1, as build.sh
openssl_ver=3.5.0
openssl_sha=344d0a79f1a9b08029b0744e2cc401a43f9c90acd1044d09a530b4885a8e9fc0
sdk=34
jobs=${JOBS:-4}
mkdir -p "$work"

sha256() { if command -v sha256sum > /dev/null; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }

case "$(uname -s)-$(uname -m)" in
	Linux-x86_64) arch=x86_64-linux; want=b761e3a0721dbae9c09a0059e5fdb2bf917d1b4a8a7b430fb3b5aafb0984b2c4 ;;
	*) echo "build_wasip2_ssl.sh: the checksum of wasi-sdk $sdk is known for Linux x86_64 only, not for $(uname -s)-$(uname -m)" >&2; exit 1 ;;
esac

if [ ! -d "$work/wasi-sdk-$sdk.0-$arch" ]; then
	curl -fsSL -o "$work/sdk.tgz" "https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-$sdk/wasi-sdk-$sdk.0-$arch.tar.gz"
	[ "$(sha256 "$work/sdk.tgz")" = "$want" ] || { echo "build_wasip2_ssl.sh: the checksum of the wasi-sdk is not $want" >&2; exit 1; }
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

# OpenSSL for wasm32-wasip2. The flags, and why:
#   linux-generic32      a plain 32-bit target with no assembly (there is no wasm target in OpenSSL)
#   no-asm no-shared no-dso no-apps no-tests no-docs   static libraries only, nothing to run, nothing to install but the headers and libs
#   no-threads           crypto/thread/arch/thread_posix.c needs pthread_exit, which wasi-libc has not (and WASI has no threads here)
#   no-quic              ssl/rio/rio_notifier.c needs socketpair, which WASI has not
#   no-async             no ucontext/makecontext
#   no-afalgeng no-ktls no-engine no-ui-console no-secure-memory   Linux-only or terminal/mmap features that WASI lacks
#   -DOPENSSL_NO_UNIX_SOCK   wasi-libc's sockaddr_un has no sun_path
#   -D_WASI_EMULATED_*   the emulated signal, process-clock and mman parts of wasi-libc (CPython links the same ones)
osrc=$work/openssl-$openssl_ver
oprefix=$work/openssl-wasip2
if [ ! -f "$oprefix/lib/libssl.a" ]; then
	if [ ! -f "$work/openssl.tgz" ]; then
		curl -fsSL -o "$work/openssl.tgz" "https://github.com/openssl/openssl/releases/download/openssl-$openssl_ver/openssl-$openssl_ver.tar.gz"
	fi
	[ "$(sha256 "$work/openssl.tgz")" = "$openssl_sha" ] || { echo "build_wasip2_ssl.sh: the checksum of openssl is not $openssl_sha" >&2; exit 1; }
	rm -rf "$osrc" "$oprefix"
	tar xzf "$work/openssl.tgz" -C "$work"
	(cd "$osrc" &&
		CC="$sdkdir/bin/clang --target=wasm32-wasip2" AR="$sdkdir/bin/llvm-ar" RANLIB="$sdkdir/bin/llvm-ranlib" \
		./Configure linux-generic32 no-threads no-asm no-shared no-dso no-apps no-tests no-docs no-afalgeng no-ui-console \
			no-secure-memory no-engine no-async no-ktls no-quic \
			-DOPENSSL_NO_UNIX_SOCK -D_WASI_EMULATED_SIGNAL -D_WASI_EMULATED_PROCESS_CLOCKS -D_WASI_EMULATED_MMAN \
			--prefix="$oprefix" --openssldir="$oprefix/ssl" > "$work/openssl-configure.log" 2>&1 &&
		make -j"$jobs" build_libs > "$work/openssl-make.log" 2>&1 &&
		make install_dev > "$work/openssl-install.log" 2>&1)
	rm -rf "$osrc" # the objects are 150 MB; the libraries are installed
fi

# CPython's _ssl.c and _hashopenssl.c refuse OpenSSL without OPENSSL_THREADS (it is not defined by a no-threads build). WASI has
# no threads, so the macro is only defined for CPython: the C flag goes to the CPython build, the OpenSSL headers stay as installed.
mkdir -p "$work/logs"
rm -rf "$src/cross-build/wasm32-wasip2" # an earlier configure of this folder (without OpenSSL) would be reused
(cd "$src" && python3 Platforms/WASI build-python --quiet --logdir "$work/logs" &&
	python3 Platforms/WASI build-host --quiet --logdir "$work/logs" --host-triple wasm32-wasip2 --wasi-sdk "$sdkdir" --host-runner true \
		ZLIB_CFLAGS="-I$zout/include" ZLIB_LIBS="-L$zout/lib -lz" -- \
		CC="$sdkdir/bin/clang --target=wasm32-wasip2" CPP="$sdkdir/bin/clang --target=wasm32-wasip2 -E" CXX="$sdkdir/bin/clang++ --target=wasm32-wasip2" \
		CPPFLAGS="-DOPENSSL_THREADS=1" --with-openssl="$oprefix")

# the component holds one core module (and the adapters, which a host that runs the module does not need): take the module out and strip it
unb=$work/unbundled
rm -rf "$unb"
mkdir -p "$unb"
wasm-tools component unbundle --threshold 0 --module-dir "$unb" -o "$unb/rest.wasm" "$src/cross-build/wasm32-wasip2/python.wasm"
ls -l "$unb/unbundled-module0.wasm"
wasm-tools strip "$unb/unbundled-module0.wasm" -o "$here/python2_ssl.wasm"
ls -l "$here/python2_ssl.wasm"
sha256 "$here/python2_ssl.wasm"
