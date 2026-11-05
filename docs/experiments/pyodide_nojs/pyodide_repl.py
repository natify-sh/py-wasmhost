#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["wasmtime>=49"]
# ///
"""A Python REPL in Pyodide's own `pyodide.asm.wasm`, run by wasmtime: no browser, no Node, none of Pyodide's JavaScript.

    uv run pyodide_repl.py                 # the REPL
    uv run pyodide_repl.py -c "print(1 + 1)"

The first start downloads the npm package `pyodide` (checked against the hash of the registry), and converts `pyodide.asm.wasm` once:
the package ships legacy WebAssembly exceptions, which wasmtime does not take, and Binaryen's `wasm-opt --translate-to-exnref`
rewrites them to the new ones. That needs `wasm-opt` (Binaryen 130 or newer) on PATH or named by `--wasm-opt` / `$WASM_OPT`
(`brew install binaryen`; `apt install binaryen` is often older; or `npm install -g binaryen`, whose `wasm-opt` runs on Node). The
script downloads no program. Everything is cached in `~/.cache/pyodide-wasmtime` (`$XDG_CACHE_HOME`).

The host answers the 254 `env` and 14 `wasi_snapshot_preview1` imports of the module in Python (files from a temporary folder, no
sandbox); the bridge to JavaScript (`js`, `pyodide.ffi`, `micropip`) is stubbed, and there are no packages and no network.
An experiment, by hand on Linux, not in CI: see docs/experiments/pyodide_nojs/README.md in py-wasmhost.
"""
# ruff: noqa: E402, E501

import argparse
import base64
import errno as E
import hashlib
import io
import json
import os
import shlex
import shutil
import stat as ST
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

from wasmtime import (
    Config,
    Engine,
    Func,
    FuncType,
    Global,
    GlobalType,
    Linker,
    Module,
    Store,
    Val,
    ValType,
    WasmtimeError,
)

PYODIDE_VERSION = "314.0.7"
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "pyodide-wasmtime" / PYODIDE_VERSION
ENV = [b"PYTHONHOME=/", b"LANG=C.UTF-8"]
ROOT = ""  # the folder that the guest sees as `/`, made in main()
cwd = ["/"]
fdpath: dict[int, str] = {}
dpos: dict[int, int] = {}
calls: dict[str, int] = {}
CUR: list = []  # the `Caller` of the host function that is running: wasmtime wants it for every access to the memory


class _Memory:
    """The memory of the guest, through the caller of the running host function."""

    def __init__(self):
        self.memory = None

    def read(self, addr, n):
        return self.memory.read(CUR[-1], addr, addr + n)

    def write(self, addr, data):
        self.memory.write(CUR[-1], bytes(data), addr)


MEM = _Memory()


def fetch() -> None:
    """pyodide.asm.wasm and python_stdlib.zip from the npm package, checked against the integrity of the registry."""
    if (CACHE / "pyodide.asm.wasm").exists() and (CACHE / "python_stdlib.zip").exists():
        return
    meta_url = f"https://registry.npmjs.org/pyodide/{PYODIDE_VERSION}"
    meta = json.load(urllib.request.urlopen(meta_url, timeout=60))["dist"]
    print(f"downloading {meta['tarball']} ...", file=sys.stderr)
    data = urllib.request.urlopen(meta["tarball"], timeout=300).read()
    algo, _, want = meta["integrity"].partition("-")
    if base64.b64encode(hashlib.new(algo, data).digest()).decode() != want:
        raise SystemExit("the npm tarball does not match its integrity hash: not used")
    CACHE.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for name in ("pyodide.asm.wasm", "python_stdlib.zip"):
            member = tar.extractfile(f"package/{name}")
            assert member is not None
            (CACHE / ("orig_" + name if name.endswith(".wasm") else name)).write_bytes(member.read())


def convert(wasm_opt: list[str]) -> None:
    """The legacy exceptions of pyodide.asm.wasm as `exnref` ones, once."""
    out = CACHE / "pyodide.asm.wasm"
    if out.exists():
        return
    print("converting the exceptions with", " ".join(wasm_opt), "(about 10 s) ...", file=sys.stderr)
    cmd = [
        *wasm_opt,
        str(CACHE / "orig_pyodide.asm.wasm"),
        "--all-features",
        "--disable-compact-imports",
        "--translate-to-exnref",
    ]
    try:
        subprocess.run([*cmd, "-o", str(out) + ".part"], check=True)
    except FileNotFoundError:
        raise SystemExit(
            f"{wasm_opt[0]} not found: install Binaryen 130 or newer (brew install binaryen, or npm install -g binaryen), "
            "or name it with --wasm-opt / $WASM_OPT"
        ) from None
    os.replace(str(out) + ".part", out)


def u32(a):
    return struct.unpack("<I", bytes(MEM.read(a, 4)))[0]


def w32(a, v):
    MEM.write(a, struct.pack("<I", v & 0xFFFFFFFF))


def w64(a, v):
    MEM.write(a, struct.pack("<Q", v & 0xFFFFFFFFFFFFFFFF))


def fd_write(fd, iov, n, out):
    total = 0
    for k in range(n):
        p, ln = u32(iov + 8 * k), u32(iov + 8 * k + 4)
        data = bytes(MEM.read(p, ln))
        total += ln
        stream = sys.stdout if fd == 1 else sys.stderr
        stream.write(data.decode("utf-8", "replace"))
        stream.flush()
    w32(out, total)
    return 0


def environ_sizes_get(pc, ps):
    w32(pc, len(ENV))
    w32(ps, sum(len(e) + 1 for e in ENV))
    return 0


def environ_get(pp, pb):
    for e in ENV:
        w32(pp, pb)
        MEM.write(pb, e + b"\0")
        pb += len(e) + 1
        pp += 4
    return 0


def clock_time_get(cid, prec, out):
    w64(out, time.time_ns() if cid == 0 else time.monotonic_ns())
    return 0


def random_get(buf, n):
    MEM.write(buf, os.urandom(n))
    return 0


def proc_exit(code):
    raise SystemExit(code)


def get_progname(buf, n):
    MEM.write(buf, b"python\0")
    return 0


def host(path_ptr_or_str, dirfd=-100):
    p = path_ptr_or_str if isinstance(path_ptr_or_str, str) else cstr(path_ptr_or_str)
    if not p.startswith("/"):
        base = cwd[0] if dirfd == -100 else fdpath[dirfd]
        p = os.path.normpath(base + "/" + p)
    return p, ROOT + os.path.normpath(p)


def cstr(a):
    out = b""
    while True:
        c = bytes(MEM.read(a + len(out), 64))
        if b"\0" in c:
            return (out + c.split(b"\0")[0]).decode()
        out += c


def neg(e):
    return -e.errno if isinstance(e, OSError) and e.errno else -E.EIO


def wstat(buf, st):
    mem = MEM
    b = bytearray(96)
    struct.pack_into(
        "<IIIIII", b, 0, st.st_dev & 0xFFFFFFFF, st.st_mode, st.st_nlink, st.st_uid, st.st_gid, st.st_rdev & 0xFFFFFFFF
    )
    struct.pack_into("<q", b, 24, st.st_size)
    struct.pack_into("<II", b, 32, 4096, st.st_blocks)
    for off, t in ((40, st.st_atime_ns), (56, st.st_mtime_ns), (72, st.st_ctime_ns)):
        struct.pack_into("<qI", b, off, t // 10**9, t % 10**9)
    struct.pack_into("<q", b, 88, st.st_ino)
    mem.write(buf, bytes(b))
    return 0


def sc_getcwd(buf, size):
    d = cwd[0].encode() + b"\0"
    if len(d) > size:
        return -E.ERANGE
    MEM.write(buf, d)
    return len(d)


def sc_openat(dirfd, path, flags, va):
    g, h = host(path, dirfd)
    try:
        fd = os.open(h, flags & ~0o2000000, 0o644)
    except OSError as e:
        return neg(e)
    fdpath[fd] = g
    return fd


def sc_stat(path, buf):
    try:
        return wstat(buf, os.stat(host(path)[1]))
    except OSError as e:
        return neg(e)


def sc_lstat(path, buf):
    try:
        return wstat(buf, os.lstat(host(path)[1]))
    except OSError as e:
        return neg(e)


def sc_fstat(fd, buf):
    try:
        return wstat(buf, os.fstat(fd))
    except OSError as e:
        return neg(e)


def sc_newfstatat(dirfd, path, buf, flags):
    try:
        h = host(path, dirfd)[1] if (isinstance(path, str) or cstr(path)) else None
        if h is None:
            return sc_fstat(dirfd, buf)
        return wstat(buf, os.lstat(h) if flags & 0x100 else os.stat(h))
    except OSError as e:
        return neg(e)


def sc_readlinkat(dirfd, path, buf, n):
    try:
        t = os.readlink(host(path, dirfd)[1]).encode()[:n]
    except OSError as e:
        return neg(e)
    MEM.write(buf, t)
    return len(t)


def sc_faccessat(dirfd, path, mode, flags):
    try:
        os.stat(host(path, dirfd)[1])
        return 0
    except OSError as e:
        return neg(e)


def sc_getdents64(fd, dirp, count):
    g = fdpath[fd]
    names = [".", ".."] + sorted(os.listdir(ROOT + g))
    pos = dpos.setdefault(fd, 0)
    out = b""
    while pos < len(names):
        n = names[pos].encode()
        rec = struct.pack("<QqHB", 1, pos + 1, 0, 0) + n + b"\0"
        rec += b"\0" * (-len(rec) % 8)
        rec = rec[:16] + b""
        st = (
            os.lstat(ROOT + os.path.normpath(g + "/" + names[pos]))
            if names[pos] not in (".", "..")
            else os.stat(ROOT + g)
        )
        typ = 4 if ST.S_ISDIR(st.st_mode) else 10 if ST.S_ISLNK(st.st_mode) else 8
        body = n + b"\0"
        ln = (19 + len(body) + 7) // 8 * 8
        rec = struct.pack("<QqHB", st.st_ino, pos + 1, ln, typ) + body
        rec += b"\0" * (ln - len(rec))
        if len(out) + ln > count:
            break
        out += rec
        pos += 1
    dpos[fd] = pos
    MEM.write(dirp, out)
    return len(out)


def fd_read(fd, iov, n, out):
    tot = 0
    for k in range(n):
        p, ln = u32(iov + 8 * k), u32(iov + 8 * k + 4)
        d = os.read(fd, ln)  # fd 0 is the terminal here
        MEM.write(p, d)
        tot += len(d)
        if len(d) < ln:
            break
    w32(out, tot)
    return 0


def fd_pread(fd, iov, n, off, out):
    tot = 0
    for k in range(n):
        p, ln = u32(iov + 8 * k), u32(iov + 8 * k + 4)
        d = os.pread(fd, ln, off + tot)
        MEM.write(p, d)
        tot += len(d)
        if len(d) < ln:
            break
    w32(out, tot)
    return 0


def fd_seek(fd, off, whence, out):
    try:
        r = os.lseek(fd, off, whence)
    except OSError as e:
        return e.errno
    w64(out, r)
    return 0


def fd_close(fd):
    try:
        os.close(fd) if fd > 2 else None
    except OSError as e:
        return e.errno
    return 0


def fd_fdstat_get(fd, buf):
    st = os.fstat(fd) if fd > 2 else None
    ft = 2 if fd <= 2 else 3 if ST.S_ISDIR(st.st_mode) else 4 if ST.S_ISREG(st.st_mode) else 0
    MEM.write(buf, struct.pack("<BxHxxxxQQ", ft, 0, 0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF))
    return 0


def sc_ioctl(fd, op, va):
    return -E.ENOTTY


def sc_fcntl(fd, cmd, va):
    return 0


def resize(n):
    """emscripten_resize_heap: grow the memory to at least `n` bytes."""
    need = -(-n // 65536) - MEM.memory.size(CUR[-1])
    try:
        if need > 0:
            MEM.memory.grow(CUR[-1], need)
    except WasmtimeError:
        return 0
    return 1


def trampoline(f, a, b, c):
    """`wasmTable.get(f)(a, b, c)` of JavaScript: the extra arguments are dropped, the missing ones are 0."""
    fn = TABLE.get(CUR[-1], f)
    ty = fn.type(CUR[-1])
    r = fn(CUR[-1], *([a, b, c] + [0, 0, 0])[: len(ty.params)])
    return r if ty.results else 0


IMPL = dict(
    fd_write=fd_write,
    environ_sizes_get=environ_sizes_get,
    environ_get=environ_get,
    clock_time_get=clock_time_get,
    random_get=random_get,
    proc_exit=proc_exit,
    _emscripten_get_progname=get_progname,
    _PyEM_TrampolineCall_JS=trampoline,
    __syscall_getcwd=sc_getcwd,
    __syscall_openat=sc_openat,
    __syscall_stat64=sc_stat,
    __syscall_lstat64=sc_lstat,
    __syscall_fstat64=sc_fstat,
    __syscall_newfstatat=sc_newfstatat,
    __syscall_readlinkat=sc_readlinkat,
    __syscall_faccessat=sc_faccessat,
    __syscall_getdents64=sc_getdents64,
    __syscall_ioctl=sc_ioctl,
    __syscall_fcntl64=sc_fcntl,
    fd_read=fd_read,
    fd_pread=fd_pread,
    fd_seek=fd_seek,
    fd_close=fd_close,
    fd_fdstat_get=fd_fdstat_get,
    emscripten_date_now=lambda: time.time() * 1000,
    emscripten_get_now=lambda: time.monotonic() * 1000,
    emscripten_get_heap_max=lambda: 0x7FFF0000,
    emscripten_resize_heap=resize,
)

_ZERO = {"i32": 0, "i64": 0, "f32": 0.0, "f64": 0.0}


def stub(name, ty):
    """Everything the module asks for and this host does not do (the bridge to JavaScript): log it, answer 0 / null."""

    def f(*args):
        calls[name] = calls.get(name, 0) + 1
        if calls[name] <= 1:
            print("STUB", name, file=sys.stderr)
        zeros = [_ZERO.get(str(r), None) for r in ty.results]
        return zeros[0] if len(zeros) == 1 else (tuple(zeros) if zeros else None)

    return f


def wrap(fn, nresults):
    """The host function with the caller kept for the memory; a function with no result must answer None."""

    def f(caller, *args):
        CUR.append(caller)
        try:
            r = fn(*args)
        finally:
            CUR.pop()
        return r if nresults else None

    return f


def main():
    global ROOT, TABLE
    ap = argparse.ArgumentParser(
        description="A Python REPL in Pyodide's pyodide.asm.wasm on wasmtime, with no JavaScript"
    )
    ap.add_argument("-c", dest="code", help="run this code and exit")
    ap.add_argument(
        "--wasm-opt", default=os.environ.get("WASM_OPT", "wasm-opt"), help="the command of Binaryen's wasm-opt"
    )
    args = ap.parse_args()
    fetch()
    convert(shlex.split(args.wasm_opt))
    ROOT = tempfile.mkdtemp(prefix="pyodide_wasmtime_")
    os.makedirs(ROOT + "/lib")
    shutil.copy(CACHE / "python_stdlib.zip", ROOT + "/lib/python314.zip")
    cfg = Config()
    cfg.wasm_exceptions = True
    engine = Engine(cfg)
    module = Module(engine, (CACHE / "pyodide.asm.wasm").read_bytes())
    store = Store(engine)
    linker = Linker(engine)
    got = {}
    for imp in module.imports:
        if isinstance(imp.type, FuncType):
            fn = IMPL.get(imp.name) or stub(imp.name, imp.type)
            linker.define_func(imp.module, imp.name, imp.type, wrap(fn, len(imp.type.results)), access_caller=True)
        elif isinstance(imp.type, GlobalType):
            got[imp.name] = Global(store, GlobalType(ValType.i32(), True), Val.i32(0))
            linker.define(store, imp.module, imp.name, got[imp.name])
    instance = linker.instantiate(store, module)
    ex = instance.exports(store)
    MEM.memory = ex["memory"]
    TABLE = ex["__indirect_function_table"]
    CUR.append(store)
    for (
        name,
        g,
    ) in got.items():  # GOT.func: the table slot of the module's own function (what the Emscripten loader does)
        try:
            fn = ex[name]
        except KeyError:
            continue
        if isinstance(fn, Func):
            g.set_value(store, TABLE.grow(store, 1, Val.funcref(fn)))
    ex["emscripten_stack_init"](store)
    ex["__wasm_call_ctors"](store)
    ex["Py_Initialize"](store)
    code = args.code or (
        "import code, sys\n"
        "code.interact(banner='Python %s (Pyodide pyodide.asm.wasm on wasmtime, no JavaScript)' % sys.version.split()[0], exitmsg='')"
    )
    raw = code.encode() + b"\0"
    p = ex["PyMem_Malloc"](store, len(raw))
    MEM.write(p, raw)
    sys.exit(0 if ex["PyRun_SimpleString"](store, p) == 0 else 1)


if __name__ == "__main__":
    main()
