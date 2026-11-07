# /// script
# requires-python = ">=3.10"
# dependencies = ["wasmtime>=50"]
# ///
"""PoC: numpy (an Emscripten wheel, loaded with a dlopen written in Python) in Pyodide's pyodide.asm.wasm on wasmtime, no JavaScript.

    uv run pyodide_numpy.py [-c CODE]          # needs `wasm-opt` on PATH: npm install -g binaryen

First run: downloads pyodide-315.0.0a2.tar.bz2 (35 MB, hash checked), takes pyodide.asm.wasm, python_stdlib.zip and the numpy wheel out
of it and converts the three modules with C++/legacy exceptions to the new exception handling (wasmtime has no legacy ones). Cached in
~/.cache/pyodide-wasmtime-numpy. Not a sandbox, not in CI.
"""

# ruff: noqa: E402, E501
import atexit
import errno as E
import hashlib
import os
import shutil
import stat as ST
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, cast

from wasmtime import (
    Caller,
    Config,
    Engine,
    Func,
    FuncType,
    Global,
    GlobalType,
    Linker,
    Memory,
    Module,
    Store,
    Val,
    ValType,
    WasmtimeError,
)

VER = "315.0.0a2"
TAR_SHA256 = "cd93f79338318074ad041747255a1a82fda7a1f775a204a8b8d42ddfc72b78f0"
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "pyodide-wasmtime-numpy" / VER


def prepare():  # download once, unpack, convert the exceptions once
    if (CACHE / "done").exists():
        return
    import urllib.request

    url = f"https://github.com/pyodide/pyodide/releases/download/{VER}/pyodide-{VER}.tar.bz2"
    data = urllib.request.urlopen(url).read()
    assert hashlib.sha256(data).hexdigest() == TAR_SHA256, "hash mismatch"
    CACHE.mkdir(parents=True, exist_ok=True)
    import io

    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        wheel = next(m for m in tar.getmembers() if m.name.startswith("pyodide/numpy-") and m.name.endswith(".whl"))
        (CACHE / "pyodide.asm.wasm").write_bytes(cast(Any, tar.extractfile("pyodide/pyodide.asm.wasm")).read())
        (CACHE / "python_stdlib.zip").write_bytes(cast(Any, tar.extractfile("pyodide/python_stdlib.zip")).read())
        zipfile.ZipFile(io.BytesIO(cast(Any, tar.extractfile(wheel)).read())).extractall(CACHE / "site")
    todo = [CACHE / "pyodide.asm.wasm"] + [
        p for p in (CACHE / "site").rglob("*.so") if p.name.startswith(("_multiarray_umath", "_pocketfft_umath"))
    ]
    for p in todo:  # the two numpy modules that throw C++ exceptions, and the main module
        subprocess.run(
            ["wasm-opt", p, "--all-features", "--disable-compact-imports", "--translate-to-exnref", "-o", p], check=True
        )
    (CACHE / "done").write_text("ok")


prepare()
PYODIDE_DIR = str(CACHE)
SITE_DIR = str(CACHE / "site")
PYVER = os.environ.get("PYVER", "3.15")
ENV = [
    b"PYTHONHOME=/",
    b"LANG=C.UTF-8",
    f"PYTHONPATH=/lib/python{PYVER}/site-packages".encode(),
    b"PYTHONDONTWRITEBYTECODE=1",
]
ROOT = tempfile.mkdtemp(prefix="pyodide_numpy_")  # what the guest sees as `/` (not a sandbox)
os.makedirs(ROOT + f"/lib/python{PYVER}")
shutil.copy(os.path.join(PYODIDE_DIR, "python_stdlib.zip"), ROOT + f"/lib/python{PYVER.replace('.', '')}.zip")
os.symlink(SITE_DIR, ROOT + f"/lib/python{PYVER}/site-packages")
atexit.register(shutil.rmtree, ROOT, True)
cwd = ["/"]
fdpath: dict[int, str] = {}
dpos: dict[int, int] = {}
calls: dict[str, int] = {}
CUR: list[
    Caller | Store
] = []  # the `Caller` of the host function that is running: wasmtime wants it for every access to the memory


class _Memory:
    """The memory of the guest, through the caller of the running host function."""

    memory: Memory  # set once the guest is instantiated

    def read(self, addr: int, n: int) -> bytes:
        return bytes(self.memory.read(CUR[-1], addr, addr + n))

    def write(self, addr: int, data: bytes | bytearray | memoryview) -> None:
        self.memory.write(CUR[-1], bytes(data), addr)


MEM = _Memory()


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
        (sys.stdout if fd == 1 else sys.stderr).write(data.decode("utf-8", "replace"))
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
    dpos.pop(fd, None)  # a new open of the same descriptor number starts the listing again
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
        d = os.read(fd, ln) if fd else b""
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
    ft = 2 if fd <= 2 or st is None else 3 if ST.S_ISDIR(st.st_mode) else 4 if ST.S_ISREG(st.st_mode) else 0
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


# ---------------------------------------------------------------- dlopen (the loader that Emscripten's JavaScript glue is)
import struct as _st

from wasmtime import Tag, TagType

LIBS: dict[Any, Any] = {}  # handle pointer -> lib; and by name
LIBS_BY_NAME: dict[str, Any] = {}
SLOTS: dict[Any, int] = {}
LOADLOG: list[str] = []
EX: Any = None  # exports of the main module
ENGINE: Any = None
STORE0: Any = None
TABLE: Any = None


def slot_of(caller, key, func):
    if key not in SLOTS:
        SLOTS[key] = TABLE.grow(caller, 1, Val.funcref(func))
    return SLOTS[key]


def parse_dylink(b):
    def leb(i):
        r = s = 0
        while True:
            c = b[i]
            i += 1
            r |= (c & 0x7F) << s
            s += 7
            if not c & 0x80:
                return r, i

    i = 8
    while i < len(b):
        sid = b[i]
        i += 1
        size, i = leb(i)
        end = i + size
        if sid == 0:
            n, j = leb(i)
            if b[j : j + n] == b"dylink.0":
                j += n
                out: dict[str, Any] = dict(memsize=0, memalign=0, tablesize=0, tablealign=0, needed=[])
                while j < end:
                    sub = b[j]
                    j += 1
                    ssz, j = leb(j)
                    if sub == 1:
                        k = j
                        for key in ("memsize", "memalign", "tablesize", "tablealign"):
                            out[key], k = leb(k)
                    elif sub == 2:
                        k = j
                        cnt, k = leb(k)
                        for _ in range(cnt):
                            ln, k = leb(k)
                            out["needed"].append(b[k : k + ln].decode())
                            k += ln
                    j += ssz
                return out
        i = end
    raise ValueError("no dylink.0")


def main_export(name):
    try:
        return EX[name]
    except KeyError:
        return None


def lookup_func(name):
    e = main_export(name)
    if isinstance(e, Func):
        return ("main", e)
    for lib in LIBS_BY_NAME.values():
        e = lib["exports"].get(name)
        if isinstance(e, Func):
            return (lib["name"], e)
    return None


def dlopen_js(handle):
    c = CUR[-1]
    path = cstr(handle + 36)
    g, h = host(path)
    lib = LIBS_BY_NAME.get(g)
    if lib is None:
        try:
            data = open(h, "rb").read()
            lib = load_side_module(c, g, data)
        except Exception as exc:  # report, answer 0: CPython raises ImportError
            import traceback

            LOADLOG.append(f"dlopen {g} FAILED {type(exc).__name__}: {exc}")
            print(f"[loader] dlopen {g} FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
            if os.environ.get("LOADER_TRACE"):
                traceback.print_exc()
            return 0
        LIBS_BY_NAME[g] = lib
    LIBS[handle] = lib
    MEM.write(handle + 8, b"\x01")
    MEM.write(handle + 12, _st.pack("<IIII", lib["base"], lib["memsize"], lib["tbase"], lib["tsize"]))
    return 1


def load_side_module(c, name, data):
    info: Any = parse_dylink(data)
    module = Module(ENGINE, data)
    size, align = info["memsize"], 1 << info["memalign"]
    raw = EX["calloc"](c, size + align, 1) if size else 0
    base = (raw + align - 1) // align * align if size else 0
    tsize = info["tablesize"]
    tbase = TABLE.size(c)
    if tsize:
        TABLE.grow(c, tsize, Val.funcref(None))
    linker = Linker(ENGINE)
    own = {e.name for e in module.exports}
    patch: list[Any] = []
    i32 = ValType.i32()
    cell: list[Any] = []
    lib: dict[str, Any] = dict(name=name, base=base, memsize=size, tbase=tbase, tsize=tsize, exports={}, missing=[])
    for imp in module.imports:
        assert imp.name is not None
        m, n, ty = imp.module, imp.name, imp.type
        if m == "env" and n == "memory":
            item = MEM.memory
        elif m == "env" and n == "__indirect_function_table":
            item = TABLE
        elif m == "env" and n == "__memory_base":
            item = Global(c, GlobalType(i32, False), Val.i32(base))
        elif m == "env" and n == "__table_base":
            item = Global(c, GlobalType(i32, False), Val.i32(tbase))
        elif m == "env" and n == "__stack_pointer":
            item = EX["__stack_pointer"]
        elif isinstance(ty, TagType):
            item = EX[n] if main_export(n) is not None else Tag(c, ty)
        elif m == "env" and isinstance(ty, FuncType):
            r = lookup_func(n)
            if r is None and n in own:  # a function of the module itself, called through its own export once it exists

                def tramp(caller, *args, _n=n, _cell=cell):
                    return _cell[0][_n](caller, *args)

                item = Func(STORE0, ty, tramp, access_caller=True)
                r = ("own", item)
            if r is None:
                lib["missing"].append(n)
                if os.environ.get("MISSING_OK"):
                    item = Func(
                        STORE0, ty, lambda *a, _n=n: (_ for _ in ()).throw(RuntimeError(f"unresolved function {_n}"))
                    )
                else:
                    raise RuntimeError(f"unresolved function import env.{n}")
            else:
                item = r[1]
        elif m in ("GOT.mem", "GOT.func"):
            item = Global(c, GlobalType(i32, True), Val.i32(0))
            if n in own:
                patch.append((item, m, n))
            else:
                e = main_export(n)
                if m == "GOT.mem" and isinstance(e, Global):
                    item.set_value(c, e.value(c))
                elif isinstance(e, Func):
                    item.set_value(c, slot_of(c, ("main", n), e))
                else:  # a symbol of a library loaded before
                    done = False
                    for other in LIBS_BY_NAME.values():
                        oe = other["exports"].get(n)
                        if m == "GOT.mem" and isinstance(oe, Global):
                            item.set_value(c, other["base"] + oe.value(c))
                            done = True
                            break
                        if m == "GOT.func" and isinstance(oe, Func):
                            item.set_value(c, slot_of(c, (other["name"], n), oe))
                            done = True
                            break
                    if not done:
                        lib["missing"].append(f"{m}.{n}")
        else:
            raise RuntimeError(f"unresolved import {m}.{n}")
        linker.define(c, m, n, item)
    inst = linker.instantiate(c, module)
    exports = inst.exports(c)
    for ex_ in module.exports:
        lib["exports"][ex_.name] = exports[ex_.name]
    cell.append(lib["exports"])
    for g_, kind, n in patch:
        e = lib["exports"][n]
        g_.set_value(c, base + e.value(c) if kind == "GOT.mem" else slot_of(c, (name, n), e))
    for hook in ("__wasm_apply_data_relocs", "__wasm_call_ctors"):
        if hook in own:
            lib["exports"][hook](c)
    LOADLOG.append(f"loaded {name}: base={base} size={size} tbase={tbase} tsize={tsize} missing={lib['missing'][:5]}")
    print(
        f"[loader] loaded {os.path.basename(name)} (mem {size}, table {tsize}, unresolved {len(lib['missing'])})",
        file=sys.stderr,
    )
    return lib


def dlsym_js(handle, sym_ptr, index_ptr):
    c = CUR[-1]
    lib = LIBS[handle]
    name = cstr(sym_ptr)
    e = lib["exports"].get(name)
    if e is None:
        return 0
    if isinstance(e, Global):
        return lib["base"] + e.value(c)
    if isinstance(e, Func):
        MEM.write(index_ptr, _st.pack("<I", list(lib["exports"]).index(name)))
        return slot_of(c, (lib["name"], name), e)
    return 0


def ffi_closure_alloc_js(size, code):
    c = CUR[-1]
    closure = EX["malloc"](c, size)
    index = TABLE.grow(c, 1, Val.funcref(None))  # an empty table slot, as getEmptyTableSlot() of the glue
    MEM.write(code, _st.pack("<I", index))
    MEM.write(closure, _st.pack("<I", index))
    return closure


def ffi_closure_free_js(closure):
    EX["free"](CUR[-1], closure)


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
    _dlopen_js=dlopen_js,
    ffi_closure_alloc_js=ffi_closure_alloc_js,
    ffi_closure_free_js=ffi_closure_free_js,
    _dlsym_js=dlsym_js,
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
    cfg = Config()
    cfg.wasm_exceptions = True
    engine = Engine(cfg)
    module = Module(engine, open(os.path.join(PYODIDE_DIR, "pyodide.asm.wasm"), "rb").read())
    store = Store(engine)
    linker = Linker(engine)
    got: dict[str, Global] = {}
    for imp in module.imports:
        assert imp.name is not None
        if isinstance(imp.type, FuncType):
            fn = IMPL.get(imp.name) or stub(imp.name, imp.type)
            linker.define_func(imp.module, imp.name, imp.type, wrap(fn, len(imp.type.results)), access_caller=True)
        elif isinstance(imp.type, GlobalType):
            got[imp.name] = Global(store, GlobalType(ValType.i32(), True), Val.i32(0))
            linker.define(store, imp.module, imp.name, got[imp.name])
    instance = linker.instantiate(store, module)
    ex: Any = instance.exports(store)
    global EX, ENGINE, STORE0
    STORE0 = store
    EX = ex
    ENGINE = engine
    MEM.memory = cast(Memory, ex["memory"])
    global TABLE
    TABLE = ex["__indirect_function_table"]
    CUR.append(store)
    slots: dict[str, int] = {}
    for (
        name,
        g,
    ) in got.items():  # GOT.func: the table slot of the module's own function (what the Emscripten loader does)
        try:
            fn = ex[name]
        except KeyError:
            continue
        if isinstance(fn, Func):
            slots[name] = TABLE.grow(store, 1, Val.funcref(fn))
            g.set_value(store, slots[name])
    ex["emscripten_stack_init"](store)
    ex["__wasm_call_ctors"](store)
    ex["Py_Initialize"](store)
    code = (
        sys.argv[2]
        if sys.argv[1:2] == ["-c"]
        else "import numpy as np; print(np.__version__, (np.arange(6.0).reshape(2, 3) @ np.ones((3, 2))).tolist())"
    ).encode() + b"\0"
    p = ex["PyMem_Malloc"](store, len(code))
    MEM.write(p, code)
    sys.exit(ex["PyRun_SimpleString"](store, p))


if __name__ == "__main__":
    main()
