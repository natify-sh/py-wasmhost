"""Experiment: numpy (a Pyodide/Emscripten wheel) on our own CPython 3.15 for wasm32-wasip1, on wasmtime-py alone: no JavaScript, no wasmhost.

    python run_cpython_numpy.py PYTHON_WASM SITE_DIR ["python code"]       # pip install wasmtime

PYTHON_WASM is `python.wasm` of `examples/cpython/build.sh` **relinked** by `relink_numpy.sh` (it exports the table, the stack pointer and
every symbol of the libc, libm and long double support that numpy's modules import, and has the small C++ runtime of `cxx_shim_np.c`).
SITE_DIR is the unpacked wheel (numpy-2.4.3-cp315-cp315-pyemscripten_2026_5_wasm32.whl of Pyodide 315.0.0a2) whose `_multiarray_umath` and
`_pocketfft_umath` went through `wasm-opt --all-features --disable-compact-imports --translate-to-exnref` (Binaryen: the old exception handling).
WASI is wasmtime's own (preview1). The loader is the one of the Pyodide experiment (now natify-sh/pyodide-wasmtime; the old `run_pyodide_numpy.py` is in the history of wasmhost), with `dlopen`/`dlsym` as the imports of the program.
By hand, not in CI: see README.md.
"""

# ruff: noqa: E402, E501, E701, E702
import atexit
import os
import shutil
import sys
import tempfile

from wasmtime import (
    Config,
    Engine,
    ExitTrap,
    Func,
    FuncType,
    Global,
    GlobalType,
    Linker,
    Module,
    Store,
    Tag,
    TagType,
    Val,
    ValType,
    WasiConfig,
)

PYWASM = os.path.abspath(sys.argv[1])
SITE = os.path.abspath(sys.argv[2])
PRELUDE = (
    "import sys, importlib.machinery as m\n"
    "sys.path_hooks.insert(0, m.FileFinder.path_hook((m.ExtensionFileLoader, m.EXTENSION_SUFFIXES + ['.cpython-315-wasm32-emscripten.so']),"
    " (m.SourceFileLoader, m.SOURCE_SUFFIXES), (m.SourcelessFileLoader, m.BYTECODE_SUFFIXES)))\n"
    "sys.path_importer_cache.clear(); sys.path.insert(0, '/lib/python3.15/site-packages')\n"
)
CODE = PRELUDE + (
    sys.argv[3] if len(sys.argv) > 3 else "import numpy as np; print('numpy', np.__version__, np.arange(10).sum())"
)
STDLIB = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "examples", "cpython", "lib", "python315.zip"
)
ROOT = tempfile.mkdtemp(prefix="cpy_numpy_")
atexit.register(shutil.rmtree, ROOT, True)
os.makedirs(ROOT + "/lib/python3.15")
shutil.copy(STDLIB, ROOT + "/lib/python315.zip")
CUR = []


class _Memory:
    def __init__(self):
        self.memory = None

    def read(self, a, n):
        return self.memory.read(CUR[-1], a, a + n)

    def write(self, a, d):
        self.memory.write(CUR[-1], bytes(d), a)


MEM = _Memory()


def cstr(a):
    out = b""
    while True:
        c = bytes(MEM.read(a + len(out), 64))
        if b"\0" in c:
            return (out + c.split(b"\0")[0]).decode()
        out += c


SP = "/lib/python3.15/site-packages"


def host(path):
    path = os.path.normpath("/" + path.lstrip("/"))
    return path, (SITE + path[len(SP) :] if path.startswith(SP) else ROOT + path)


TAGS = {}
HANDLES = {}
LIBS = {}  # handle pointer -> lib; and by name
LIBS_BY_NAME = {}
SLOTS = {}
LOADLOG = []
EX = None
ENGINE = None


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
                out = dict(memsize=0, memalign=0, tablesize=0, tablealign=0, needed=[])
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


def dlopen_new(path_ptr, flags):
    c = CUR[-1]
    path = cstr(path_ptr)
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
    handle = len(HANDLES) + 1
    HANDLES[handle] = lib
    return handle


def load_side_module(c, name, data):
    info = parse_dylink(data)
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
    patch = []
    i32 = ValType.i32()
    cell = []
    lib = dict(name=name, base=base, memsize=size, tbase=tbase, tsize=tsize, exports={}, missing=[])
    for imp in module.imports:
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
            item = TAGS.setdefault(n, Tag(c, ty))
        elif m == "env" and isinstance(ty, FuncType):
            r = lookup_func(n)
            if r is None and n in own:  # a function of the module itself, called through its own export once it exists

                def tramp(caller, *args, _n=n, _cell=cell):
                    return _cell[0][_n](caller, *args)

                item = Func(STORE0, ty, tramp, access_caller=True)
                r = ("own", item)
            if r is None and n in FALLBACK:
                r = ("host", Func(STORE0, ty, FALLBACK[n]))
            if r is None and n == "fiprintf":
                r = lookup_func("fprintf")
            if r is None:
                lib["missing"].append(n)
                if True:
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
                    if not done and n == "__wasm_lpad_context":
                        item.set_value(c, EX["calloc"](c, 16, 1))
                        done = True
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


def dlsym_new(handle, sym_ptr):
    c = CUR[-1]
    lib = HANDLES[handle]
    name = cstr(sym_ptr)
    e = lib["exports"].get(name)
    if e is None:
        return 0
    if isinstance(e, Global):
        return lib["base"] + e.value(c)
    if isinstance(e, Func):
        return slot_of(c, (lib["name"], name), e)
    return 0


def _fpclassifyl(lo, hi):
    e = (hi >> 48) & 0x7FFF
    m = ((hi & 0xFFFFFFFFFFFF) << 64) | lo
    if e == 0:
        return 2 if m == 0 else 3
    if e == 0x7FFF:
        return 1 if m == 0 else 0
    return 4


FALLBACK = {"__fpclassifyl": _fpclassifyl, "__signbitl": lambda lo, hi: int((hi >> 63) & 1)}


def dlerror():
    return 0


def wrap(fn):
    def f(caller, *a):
        CUR.append(caller)
        try:
            return fn(*a)
        finally:
            CUR.pop()

    return f


cfg = Config()
cfg.wasm_exceptions = True
ENGINE = Engine(cfg)
store = Store(ENGINE)
STORE0 = store
wasi = WasiConfig()
wasi.argv = ["python", "-c", CODE]
wasi.env = [("PYTHONHOME", "/"), ("PYTHONDONTWRITEBYTECODE", "1")]
wasi.preopen_dir(ROOT, "/")
wasi.preopen_dir(SITE, SP, False)
wasi.inherit_stdout()
wasi.inherit_stderr()
store.set_wasi(wasi)
linker = Linker(ENGINE)
linker.define_wasi()
i32 = ValType.i32()
linker.define_func("env", "dlopen", FuncType([i32, i32], [i32]), wrap(dlopen_new), access_caller=True)
linker.define_func("env", "dlsym", FuncType([i32, i32], [i32]), wrap(dlsym_new), access_caller=True)
linker.define_func("env", "dlerror", FuncType([], [i32]), wrap(dlerror), access_caller=True)
inst = linker.instantiate(store, Module(ENGINE, open(PYWASM, "rb").read()))
EX = inst.exports(store)
MEM.memory = EX["memory"]
TABLE = EX["__indirect_function_table"]
CUR.append(store)
try:
    EX["_start"](store)
    code = 0
except ExitTrap as e:
    code = e.code
print("exit", code)
