"""Experiment: Pyodide's own pyodide.asm.wasm run by a Python host, with none of Pyodide's JavaScript.

    WASMHOST_BACKEND=node python run_pyodide_nojs.py PYODIDE_DIR ["python code"]

PYODIDE_DIR holds pyodide.asm.wasm and python_stdlib.zip (the npm package `pyodide`). The engine (node) is only the
WebAssembly runtime: the 254 `env` and 14 `wasi_snapshot_preview1` imports are answered by the Python functions below,
the
280 `GOT.func` globals are patched by hand (the module is an Emscripten main module), and the files come from a folder.
Needs `wasm-tools` on PATH (the types of the table entries, for the trampoline).
Not a test, not in CI: see README.md."""
# ruff: noqa: E402

import os
import struct
import sys
import time

import wasmhost
from wasmhost import Global, Instance, Module

PYODIDE_DIR = sys.argv[1]
W = os.path.join(PYODIDE_DIR, "pyodide.asm.wasm")
m = Module(open(W, "rb").read())
im = Module.imports(m)
calls = {}
state = {}


def u32(a):
    return struct.unpack("<I", bytes(state["mem"].read(a, 4)))[0]


def w32(a, v):
    state["mem"].write(a, struct.pack("<I", v & 0xFFFFFFFF))


def w64(a, v):
    state["mem"].write(a, struct.pack("<Q", v & 0xFFFFFFFFFFFFFFFF))


def fd_write(fd, iov, n, out):
    total = 0
    for k in range(n):
        p, ln = u32(iov + 8 * k), u32(iov + 8 * k + 4)
        data = bytes(state["mem"].read(p, ln))
        total += ln
        (sys.stdout if fd == 1 else sys.stderr).write(data.decode("utf-8", "replace"))
    w32(out, total)
    return 0


ENV = [b"PYTHONHOME=/", b"LANG=C.UTF-8"]


def environ_sizes_get(pc, ps):
    w32(pc, len(ENV))
    w32(ps, sum(len(e) + 1 for e in ENV))
    return 0


def environ_get(pp, pb):
    for e in ENV:
        w32(pp, pb)
        state["mem"].write(pb, e + b"\0")
        pb += len(e) + 1
        pp += 4
    return 0


def clock_time_get(cid, prec, out):
    w64(out, time.time_ns() if cid == 0 else time.monotonic_ns())
    return 0


def random_get(buf, n):
    state["mem"].write(buf, os.urandom(n))
    return 0


def proc_exit(code):
    raise SystemExit(code)


def get_progname(buf, n):
    state["mem"].write(buf, b"python\0")
    return 0


import re
import subprocess

from wasmhost import FuncType

_wat = subprocess.run(["wasm-tools", "print", W], capture_output=True, text=True).stdout
_ftype = {}
for mo in re.finditer(r"\(func \(;(\d+);\) \(type \d+\)((?: \(param [^)]*\))*)((?: \(result [^)]*\))*)", _wat):
    ps = [t for g in re.findall(r"\(param ([^)]*)\)", mo.group(2)) for t in g.split()]
    rs = [t for g in re.findall(r"\(result ([^)]*)\)", mo.group(3)) for t in g.split()]
    _ftype[int(mo.group(1))] = (tuple(ps), tuple(rs))
_slot = {}
for mo in re.finditer(r"\(elem \(;\d+;\) \(i32\.const (\d+)\) func ([\d ]+)\)", _wat):
    base = int(mo.group(1))
    for k, fi in enumerate(mo.group(2).split()):
        _slot[base + k] = int(fi)
print("table slots with a type:", len(_slot), file=sys.stderr)
_T = {"i32": wasmhost.i32, "i64": wasmhost.i64, "f32": wasmhost.f32, "f64": wasmhost.f64}


def trampoline(f, a, b, c):
    # what `wasmTable.get(f)(a, b, c)` does in JavaScript: extra arguments are dropped, missing ones are 0
    ps, rs = _ftype[_slot[f]]
    fn = state["tab"].get(f)
    fn.signature = FuncType(tuple(_T[t] for t in ps), tuple(_T[t] for t in rs))
    r = fn(*([a, b, c] + [0, 0, 0])[: len(ps)])
    return r if rs else 0


IMPL = dict(
    fd_write=fd_write,
    environ_sizes_get=environ_sizes_get,
    environ_get=environ_get,
    clock_time_get=clock_time_get,
    random_get=random_get,
    proc_exit=proc_exit,
    _emscripten_get_progname=get_progname,
    _PyEM_TrampolineCall_JS=trampoline,
)


import shutil
import tempfile

ROOT = tempfile.mkdtemp(prefix="pyodide_nojs_")
os.makedirs(ROOT + "/lib")
shutil.copy(os.path.join(PYODIDE_DIR, "python_stdlib.zip"), ROOT + "/lib/python314.zip")
import errno as E
import stat as ST

cwd = ["/"]


def host(path_ptr_or_str, dirfd=-100):
    p = path_ptr_or_str if isinstance(path_ptr_or_str, str) else cstr(path_ptr_or_str)
    if not p.startswith("/"):
        base = cwd[0] if dirfd == -100 else fdpath[dirfd]
        p = os.path.normpath(base + "/" + p)
    return p, ROOT + os.path.normpath(p)


fdpath = {}


def cstr(a):
    out = b""
    while True:
        c = bytes(state["mem"].read(a + len(out), 64))
        if b"\0" in c:
            return (out + c.split(b"\0")[0]).decode()
        out += c


def neg(e):
    return -e.errno if isinstance(e, OSError) and e.errno else -E.EIO


def wstat(buf, st):
    mem = state["mem"]
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
    state["mem"].write(buf, d)
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
    state["mem"].write(buf, t)
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
    state["mem"].write(dirp, out)
    return len(out)


dpos = {}


def fd_read(fd, iov, n, out):
    tot = 0
    for k in range(n):
        p, ln = u32(iov + 8 * k), u32(iov + 8 * k + 4)
        d = os.read(fd, ln) if fd else b""
        state["mem"].write(p, d)
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
        state["mem"].write(p, d)
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
    state["mem"].write(buf, struct.pack("<BxHxxxxQQ", ft, 0, 0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF))
    return 0


def sc_ioctl(fd, op, va):
    return -E.ENOTTY


def sc_fcntl(fd, cmd, va):
    return 0


def resize(n):
    """emscripten_resize_heap: grow the memory to at least `n` bytes."""
    mem = state["mem"]
    need = -(-n // 65536) - mem.grow(0)  # Memory.grow answers the old size in pages
    try:
        if need > 0:
            mem.grow(need)
    except Exception:
        return 0
    return 1


IMPL.update(
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


def stub(name, nres):
    def f(*a):
        calls[name] = calls.get(name, 0) + 1
        if calls[name] <= 2:
            print("STUB", name, a, file=sys.stderr)
        return 0 if nres else None

    return f


env = {}
for i in im:
    if i.kind == "function":
        env.setdefault(i.module, {})[i.name] = IMPL.get(i.name) or stub(i.name, len(i.type.results))
    elif i.kind == "global":
        env.setdefault(i.module, {})[i.name] = Global("i32", 0, mutable=True)
inst = Instance(m, env)
ex = inst.exports
state["mem"] = ex["memory"]
state["tab"] = ex["__indirect_function_table"]
slots = {}
for i in im:
    if i.kind == "global" and i.module == "GOT.func":
        try:
            fn = ex[i.name]
        except KeyError:
            continue
        slots[i.name] = state["tab"].grow(1, fn)
        env["GOT.func"][i.name].value = slots[i.name]
ex["emscripten_stack_init"]()
ex["__wasm_call_ctors"]()
try:
    ex["Py_Initialize"]()
    print("Py_Initialize returned")
    code = (
        sys.argv[2]
        if len(sys.argv) > 2
        else "import sys; print('hello from pyodide.asm.wasm, no Pyodide JS:', sys.version); print(sum(range(10)))"
    ).encode() + b"\0"
    p = ex["PyMem_Malloc"](len(code))
    state["mem"].write(p, code)
    print("PyRun_SimpleString ->", ex["PyRun_SimpleString"](p))
except BaseException as e:
    print("Py_Initialize FAILED", type(e).__name__, str(e)[:300])
print("stubs called:", sorted(calls.items(), key=lambda x: -x[1])[:20])
