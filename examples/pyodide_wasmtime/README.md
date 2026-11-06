# Pyodide on wasmtime, no JavaScript (PoC)

A Python REPL in the real `pyodide.asm.wasm`, run by **wasmtime** (the `wasmtime` Python package). No browser, no Node, none of Pyodide's JavaScript.
**A PoC, not a product:** checked by hand on Linux (wasmtime-py 49, Pyodide 314.0.7 = Python 3.14.2), not in CI.

## Run
Needs `uv` and `npm`.

```sh
npm install -g binaryen      # gives `wasm-opt` (version 132 tested)
uv run pyodide_repl.py       # the REPL; or: uv run pyodide_repl.py -c "print(1 + 1)"
```
The first run downloads the Pyodide npm package (hash checked), converts `pyodide.asm.wasm` once with `wasm-opt` and caches it in `~/.cache/pyodide-wasmtime` (about a minute; later runs a few seconds).

**Why `wasm-opt`:** the official module uses legacy exceptions (`try`/`catch`), which wasmtime 49 rejects (`legacy_exceptions feature required for try instruction`).
`wasm-opt --translate-to-exnref` rewrites them once into the new ones. (`--disable-compact-imports` is needed too, or wasmtime cannot read the output.)

## `pyodide_repl.py`
```python
# /// script
# requires-python = ">=3.10"
# dependencies = ["wasmtime>=49"]
# ///
"""PoC: a Python REPL in Pyodide's pyodide.asm.wasm on wasmtime, no JavaScript.  Usage: uv run pyodide_repl.py [-c CODE]
Needs `wasm-opt` on PATH (`npm install -g binaryen`): wasmtime has no legacy exceptions,
and wasm-opt converts the module once."""

import base64
import hashlib
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

from wasmtime import Config, Engine, Func, FuncType, Global, GlobalType, Linker, Module, Store, Val, ValType

VER = "314.0.7"
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "pyodide-wasmtime" / VER
ROOT = tempfile.mkdtemp()  # what the guest sees as `/` (not a sandbox)
cur: list = []  # the Caller of the running host function
mem = None  # the guest memory
table = None


def rd(a, n):
    return bytes(mem.read(cur[-1], a, a + n))


def wr(a, b):
    mem.write(cur[-1], bytes(b), a)


def u32(a):
    return struct.unpack("<I", rd(a, 4))[0]


def w32(a, v):
    wr(a, struct.pack("<I", v & 0xFFFFFFFF))


def cstr(a):
    out = b""
    while b"\0" not in (c := rd(a + len(out), 64)):
        out += c
    return (out + c.split(b"\0")[0]).decode()


def path(p):  # the guest path as a host path
    return ROOT + os.path.normpath("/" + cstr(p))


def fd_write(fd, iov, n, out):
    total = 0
    for k in range(n):
        data = rd(u32(iov + 8 * k), u32(iov + 8 * k + 4))
        (sys.stdout if fd == 1 else sys.stderr).write(data.decode("utf-8", "replace"))
        (sys.stdout if fd == 1 else sys.stderr).flush()
        total += len(data)
    w32(out, total)
    return 0


def fd_read(fd, iov, n, out):
    total = 0
    for k in range(n):
        p, ln = u32(iov + 8 * k), u32(iov + 8 * k + 4)
        d = os.read(fd, ln)
        wr(p, d)
        total += len(d)
        if len(d) < ln:
            break
    w32(out, total)
    return 0


def fd_pread(fd, iov, n, off, out):
    p, ln = u32(iov), u32(iov + 4)
    d = os.pread(fd, ln, off)
    wr(p, d)
    w32(out, len(d))
    return 0


def fd_seek(fd, off, whence, out):
    try:
        wr(out, struct.pack("<Q", os.lseek(fd, off, whence)))
    except OSError:
        return 70  # WASI ESPIPE: a terminal or a pipe
    return 0


def stat_into(buf, st):
    b = bytearray(96)
    struct.pack_into("<IIIIII", b, 0, st.st_dev & 0xFFFFFFFF, st.st_mode, st.st_nlink, st.st_uid, st.st_gid, 0)
    struct.pack_into("<q", b, 24, st.st_size)
    struct.pack_into("<II", b, 32, 4096, st.st_blocks)
    for off, t in ((40, st.st_atime_ns), (56, st.st_mtime_ns), (72, st.st_ctime_ns)):
        struct.pack_into("<qI", b, off, t // 10**9, t % 10**9)
    struct.pack_into("<q", b, 88, st.st_ino)
    wr(buf, b)
    return 0


def errno_of(fn, *a):
    try:
        return fn(*a)
    except OSError as e:
        return -(e.errno or 5)


def environ_sizes_get(pc, ps):
    w32(pc, 2)
    w32(ps, 24)
    return 0


def environ_get(pp, pb):
    for e in (b"PYTHONHOME=/", b"LANG=C.UTF-8"):
        w32(pp, pb)
        wr(pb, e + b"\0")
        pb, pp = pb + len(e) + 1, pp + 4
    return 0


def resize(n):
    cur_pages = mem.size(cur[-1])
    try:
        mem.grow(cur[-1], max(0, -(-n // 65536) - cur_pages))
    except Exception:
        return 0
    return 1


def trampoline(f, a, b, c):  # JavaScript's `wasmTable.get(f)(a, b, c)`: extra arguments dropped, missing ones are 0
    fn = table.get(cur[-1], f)
    ty = fn.type(cur[-1])
    r = fn(cur[-1], *([a, b, c] + [0, 0, 0])[: len(ty.params)])
    return r if ty.results else 0


IMPL = dict(
    fd_write=fd_write,
    fd_read=fd_read,
    fd_pread=fd_pread,
    fd_seek=fd_seek,
    fd_close=lambda fd: 0,
    fd_fdstat_get=lambda fd, buf: (wr(buf, struct.pack("<BxHxxxxQQ", 2 if fd < 3 else 4, 0, 2**64 - 1, 2**64 - 1)), 0)[
        1
    ],
    environ_sizes_get=environ_sizes_get,
    environ_get=environ_get,
    clock_time_get=lambda cid, prec, out: (wr(out, struct.pack("<Q", time.time_ns())), 0)[1],
    random_get=lambda buf, n: (wr(buf, os.urandom(n)), 0)[1],
    proc_exit=lambda code: sys.exit(code),
    _emscripten_get_progname=lambda buf, n: (wr(buf, b"python\0"), 0)[1],
    _PyEM_TrampolineCall_JS=trampoline,
    emscripten_resize_heap=resize,
    emscripten_date_now=lambda: time.time() * 1000,
    emscripten_get_now=lambda: time.monotonic() * 1000,
    emscripten_get_heap_max=lambda: 0x7FFF0000,
    __syscall_getcwd=lambda buf, size: (wr(buf, b"/\0"), 2)[1],
    __syscall_openat=lambda d, p, flags, va: errno_of(os.open, path(p), flags & ~0o2000000, 0o644),
    __syscall_stat64=lambda p, buf: errno_of(lambda: stat_into(buf, os.stat(path(p)))),
    __syscall_lstat64=lambda p, buf: errno_of(lambda: stat_into(buf, os.lstat(path(p)))),
    __syscall_fstat64=lambda fd, buf: errno_of(lambda: stat_into(buf, os.fstat(fd))),
    __syscall_newfstatat=lambda d, p, buf, fl: errno_of(lambda: stat_into(buf, os.stat(path(p)))),
    __syscall_ioctl=lambda fd, op, va: -25,  # ENOTTY
)


def stub(ty):  # everything else (the bridge to JavaScript): answer 0
    zero = {"i32": 0, "i64": 0, "f32": 0.0, "f64": 0.0}
    res = [zero.get(str(r)) for r in ty.results]
    return lambda *a: (res[0] if len(res) == 1 else tuple(res)) if res else None


def wrap(fn, ty):
    def f(caller, *a):
        cur.append(caller)
        try:
            r = fn(*a)
        finally:
            cur.pop()
        return r if ty.results else None

    return f


def prepare():  # npm package -> pyodide.asm.wasm converted to the new exceptions, once
    if (CACHE / "pyodide.asm.wasm").exists():
        return
    meta = json.load(urllib.request.urlopen(f"https://registry.npmjs.org/pyodide/{VER}"))["dist"]
    data = urllib.request.urlopen(meta["tarball"]).read()
    algo, _, want = meta["integrity"].partition("-")
    assert base64.b64encode(hashlib.new(algo, data).digest()).decode() == want, "npm hash mismatch"
    CACHE.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for name in ("pyodide.asm.wasm", "python_stdlib.zip"):
            (CACHE / name).write_bytes(tar.extractfile(f"package/{name}").read())
    os.replace(CACHE / "pyodide.asm.wasm", CACHE / "orig.wasm")
    subprocess.run(
        [
            "wasm-opt",
            CACHE / "orig.wasm",
            "--all-features",
            "--disable-compact-imports",
            "--translate-to-exnref",
            "-o",
            CACHE / "pyodide.asm.wasm",
        ],
        check=True,
    )


def main():
    global mem, table
    prepare()
    os.makedirs(ROOT + "/lib")
    shutil.copy(CACHE / "python_stdlib.zip", ROOT + "/lib/python314.zip")
    cfg = Config()
    cfg.wasm_exceptions = True
    engine = Engine(cfg)
    module = Module(engine, (CACHE / "pyodide.asm.wasm").read_bytes())
    store = Store(engine)
    linker, got = Linker(engine), {}
    for i in module.imports:
        if isinstance(i.type, FuncType):
            linker.define_func(
                i.module, i.name, i.type, wrap(IMPL.get(i.name) or stub(i.type), i.type), access_caller=True
            )
        elif isinstance(i.type, GlobalType):  # GOT.func: table slots of the module's own functions
            got[i.name] = Global(store, GlobalType(ValType.i32(), True), Val.i32(0))
            linker.define(store, i.module, i.name, got[i.name])
    ex = linker.instantiate(store, module).exports(store)
    mem, table = ex["memory"], ex["__indirect_function_table"]
    cur.append(store)
    for name, g in got.items():
        try:
            fn = ex[name]
        except KeyError:
            continue
        if isinstance(fn, Func):
            g.set_value(store, table.grow(store, 1, Val.funcref(fn)))
    ex["emscripten_stack_init"](store)
    ex["__wasm_call_ctors"](store)
    ex["Py_Initialize"](store)
    code = (
        sys.argv[2]
        if sys.argv[1:2] == ["-c"]
        else "import code; code.interact(banner='Pyodide on wasmtime, no JS', exitmsg='')"
    )
    raw = code.encode() + b"\0"
    p = ex["PyMem_Malloc"](store, len(raw))
    wr(p, raw)
    sys.exit(ex["PyRun_SimpleString"](store, p))


main()
```

## Not implemented
- Only 28 of the module's 268 function imports are answered; the rest are stubs. Files are a temporary folder (no sandbox, `os.listdir("/")` is empty: no `getdents64`); no network, no `dlopen` in this script (see NUMPY.md for a version with it).
- The bridge to JavaScript (`js`, `pyodide.ffi`, `micropip`; about 130 imports) cannot exist without JS.
- Possible with more work, not tried: more file calls, sockets, `dlopen` (a loader of this kind ran emscripten wheels in a different CPython build).
- Only the exception paths of these programs were exercised after the conversion; the conversion is Binaryen's. Linux only, REPL tried through a pipe.

## numpy
A version with numpy and a `dlopen` written in Python: [NUMPY.md](NUMPY.md) (script: `pyodide_numpy.py`).
