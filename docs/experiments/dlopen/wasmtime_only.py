"""The dlopen experiment on wasmtime-py alone: no wasmhost, no fusedwasi, no JavaScript.

    python wasmtime_only.py [main_dl.wasm]        # after build.sh; needs only `pip install wasmtime`

A wasi-sdk program (`main_dl.c`) calls the real `dlopen`/`dlsym`, which are imports of the host. The loader below is the
whole dynamic linker: it reads the `dylink.0` section of a side module, gives it a place in the memory of the program
(from the program's own `aligned_alloc`), grows the program's table for it, makes the `GOT.mem`/`GOT.func` globals, and
instantiates it with the memory, table and stack pointer **of the program**. WASI is wasmtime's own
(`Linker.define_wasi`, preview1). By hand, not in CI. Tested with wasmtime-py 49.0.0.
"""

import os
import sys

from wasmtime import (
    Engine,
    FuncType,
    Global,
    GlobalType,
    Linker,
    Module,
    Store,
    Val,
    ValType,
    WasiConfig,
)


def leb(b, i):
    r = s = 0
    while True:
        c = b[i]
        i += 1
        r |= (c & 0x7F) << s
        s += 7
        if not c & 0x80:
            return r, i


def parse_dylink(b):
    """The memory and table sizes (and alignments) from the `dylink.0` custom section of a side module."""
    assert b[:4] == b"\0asm"
    i = 8
    while i < len(b):
        sid = b[i]
        i += 1
        size, i = leb(b, i)
        end = i + size
        if sid == 0:
            n, j = leb(b, i)
            if b[j : j + n] == b"dylink.0":
                j += n
                out = dict(memsize=0, memalign=0, tablesize=0, tablealign=0)
                while j < end:
                    sub = b[j]
                    j += 1
                    ssz, j = leb(b, j)
                    if sub == 1:  # WASM_DYLINK_MEM_INFO
                        k = j
                        for key in ("memsize", "memalign", "tablesize", "tablealign"):
                            out[key], k = leb(b, k)
                    j += ssz
                return out
        i = end
    raise ValueError("not a side module: no dylink.0 section")


class Loader:
    def __init__(self, engine, libdir):
        self.engine, self.libdir = engine, libdir
        self.main = None  # the exports of the program
        self.libs = {}  # handle -> (instance exports, memory base)
        self.slots = {}  # id of a function -> its slot in the table

    def attach(self, store, instance):
        self.main = instance.exports(store)
        self.mem = self.main["memory"]
        self.table = self.main["__indirect_function_table"]

    def cstr(self, caller, p):
        out = b""
        while True:
            c = bytes(self.mem.read(caller, p + len(out), p + len(out) + 64))
            if b"\0" in c:
                return (out + c.split(b"\0")[0]).decode()
            out += c

    def slot(self, caller, func):
        """A table index that holds `func` (the table grows by one)."""
        key = id(func)
        if key not in self.slots:
            self.slots[key] = self.table.grow(caller, 1, Val.funcref(func))
        return self.slots[key]

    def dl_open(self, caller, path_ptr, flags):
        path = self.cstr(caller, path_ptr)
        data = open(os.path.join(self.libdir, path), "rb").read()
        info = parse_dylink(data)
        module = Module(self.engine, data)
        size, align = info["memsize"], 1 << info["memalign"]
        base = 0
        if size:  # from the program's own allocator, so that its malloc never hands the same bytes out again
            base = self.main["aligned_alloc"](caller, max(align, 16), size)
            self.mem.write(caller, bytes(size), base)  # the bss is zero
        tsize = info["tablesize"]
        tbase = self.table.grow(caller, tsize, Val.funcref(None)) if tsize else self.table.size(caller)
        linker = Linker(self.engine)
        own = {e.name for e in module.exports}
        patch = []  # (global, kind, name): symbols of the module itself, patched once it exists
        i32 = ValType.i32()
        for imp in module.imports:
            m, n, ty = imp.module, imp.name, imp.type
            if m == "env" and n == "memory":
                item = self.mem
            elif m == "env" and n == "__indirect_function_table":
                item = self.table
            elif m == "env" and n == "__memory_base":
                item = Global(caller, GlobalType(i32, False), Val.i32(base))
            elif m == "env" and n == "__table_base":
                item = Global(caller, GlobalType(i32, False), Val.i32(tbase))
            elif m == "env" and n == "__stack_pointer":
                item = self.main["__stack_pointer"]
            elif m == "env" and isinstance(ty, FuncType):
                item = self.main[n]  # KeyError: an unresolved symbol
            elif m in ("GOT.mem", "GOT.func"):
                item = Global(caller, GlobalType(i32, True), Val.i32(0))
                if n in own:
                    patch.append((item, m, n))
                elif m == "GOT.mem":
                    item.set_value(caller, self.main[n].value(caller))  # the address of a data symbol of the program
                else:
                    item.set_value(
                        caller, self.slot(caller, self.main[n])
                    )  # a function of the program, as a table index
            else:
                raise RuntimeError(f"unresolved import {m}.{n}")
            linker.define(caller, m, n, item)
        exports = linker.instantiate(caller, module).exports(caller)
        for g, kind, n in patch:
            e = exports[n]
            g.set_value(caller, base + e.value(caller) if kind == "GOT.mem" else self.slot(caller, e))
        for hook in ("__wasm_apply_data_relocs", "__wasm_call_ctors"):
            if hook in own:
                exports[hook](caller)
        handle = len(self.libs) + 1
        self.libs[handle] = (exports, base)
        print(
            f"[loader] dlopen({path}): memory_base={base} (size {size}), table_base={tbase} (size {tsize})",
            file=sys.stderr,
        )
        return handle

    def dl_sym(self, caller, handle, name_ptr):
        exports, base = self.libs[handle]
        e = exports[self.cstr(caller, name_ptr)]
        return base + e.value(caller) if isinstance(e, Global) else self.slot(caller, e)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    wasm = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "main_dl.wasm")
    engine = Engine()
    loader = Loader(engine, here)
    store = Store(engine)
    wasi = WasiConfig()
    wasi.argv = ["main"]
    wasi.inherit_stdout()
    wasi.inherit_stderr()
    store.set_wasi(wasi)
    linker = Linker(engine)
    linker.define_wasi()
    i32 = ValType.i32()
    linker.define_func("env", "dlopen", FuncType([i32, i32], [i32]), loader.dl_open, access_caller=True)
    linker.define_func("env", "dlsym", FuncType([i32, i32], [i32]), loader.dl_sym, access_caller=True)
    linker.define_func("env", "dlerror", FuncType([], [i32]), lambda: 0)
    instance = linker.instantiate(store, Module(engine, open(wasm, "rb").read()))
    loader.attach(store, instance)
    try:
        instance.exports(store)["_start"](store)
        code = 0
    except Exception as exc:  # proc_exit comes back as an Exit trap
        code = getattr(exc, "code", None)
        if code is None:
            raise
    print("exit code", code)
    return code


if __name__ == "__main__":
    sys.exit(main())
