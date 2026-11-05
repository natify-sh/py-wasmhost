"""Experiment: a dynamic loader for wasm side modules (tool-conventions DynamicLinking.md), in Python, on wasmhost's
public API only. Main module: plain wasi-sdk core module that exports memory, __indirect_function_table,
__stack_pointer, malloc/aligned_alloc and the symbols side modules use."""

import os

import wasmhost
from wasmhost import Global, Instance, Module
from wasmhost.wasi.preview1 import Preview1


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
    """-> dict(memsize, memalign, tablesize, tablealign, needed) from the `dylink.0` custom section."""
    assert b[:4] == b"\0asm"
    i = 8
    while i < len(b):
        sid = b[i]
        i += 1
        size, i = leb(b, i)
        end = i + size
        if sid == 0:
            n, j = leb(b, i)
            name = b[j : j + n].decode()
            j += n
            if name == "dylink.0":
                out = dict(memsize=0, memalign=0, tablesize=0, tablealign=0, needed=[])
                while j < end:
                    sub = b[j]
                    j += 1
                    ssz, j = leb(b, j)
                    k, send = j, j + ssz
                    if sub == 1:  # WASM_DYLINK_MEM_INFO
                        out["memsize"], k = leb(b, k)
                        out["memalign"], k = leb(b, k)
                        out["tablesize"], k = leb(b, k)
                        out["tablealign"], k = leb(b, k)
                    elif sub == 2:  # NEEDED
                        cnt, k = leb(b, k)
                        for _ in range(cnt):
                            size, k = leb(b, k)
                            out["needed"].append(b[k : k + size].decode())
                            k += size
                    j = send
                return out
        i = end
    raise ValueError("no dylink.0 section: not a side module")


class Loader:
    def __init__(self, libdir):
        self.libdir = libdir
        self.main = None
        self.libs = {}  # handle -> dict(instance, base, exports)
        self.next = 1
        self.func_slot = {}  # id(Function)/name -> table index
        self.log = []

    def attach(self, main):
        self.main = main
        self.mem = main.exports["memory"]
        self.table = main.exports["__indirect_function_table"]

    # --- helpers
    def cstr(self, p):
        out = b""
        while True:
            c = self.mem.read(p, 64)
            if b"\0" in c:
                return (out + c.split(b"\0")[0]).decode()
            out += c
            p += 64

    def slot(self, fn):
        """A table index holding `fn` (grows the table by one)."""
        key = (id(fn), getattr(fn, "name", None))
        if key not in self.func_slot:
            self.func_slot[key] = self.table.grow(1, fn)
        return self.func_slot[key]

    def hostpath(self, guest):
        """The host file of a guest path: the longest preopen name that is a prefix of it."""
        for name, host in sorted(self.libdir.items(), key=lambda kv: -len(kv[0])):
            if guest == name or guest.startswith(name.rstrip("/") + "/"):
                return os.path.join(host, guest[len(name) :].lstrip("/"))
        raise FileNotFoundError(guest)

    def alloc(self, align, size):
        """Memory for a side module, from the allocator of the main (malloc if it exports one, else cabi_realloc)."""
        ex = self.main.exports
        if "aligned_alloc" in ex:
            return ex["aligned_alloc"](align, size)
        return ex["cabi_realloc"](0, 0, align, size)

    def libc_fallback(self, n):
        """main export, else a small libc function the main did not keep (host-side, for the experiment)."""
        try:
            return self.main_export(n)
        except KeyError:
            pass
        m = self.mem
        host = {
            "ntohs": lambda x: ((x & 0xFF) << 8 | (x >> 8) & 0xFF),
            "ntohl": lambda x: int.from_bytes((x & 0xFFFFFFFF).to_bytes(4, "little"), "big"),
            "memcmp": lambda a, b, k: (lambda x, y: (x > y) - (x < y))(bytes(m.read(a, k)), bytes(m.read(b, k))),
            "strrchr": lambda p, c: (lambda s: p + s.rfind(bytes([c & 255])) if s.rfind(bytes([c & 255])) >= 0 else 0)(
                self.cbytes(p) + b"\0" if (c & 255) == 0 else self.cbytes(p)
            ),
        }
        if n in host:
            self.log.append(f"host libc fallback: {n}")
            return host[n]
        raise KeyError(n)

    def cbytes(self, p):
        out = b""
        while True:
            c = bytes(self.mem.read(p + len(out), 64))
            if b"\0" in c:
                return out + c.split(b"\0")[0]
            out += c

    def main_export(self, name):
        return self.main.exports[name]

    # --- dlopen
    def dl_open(self, path_ptr):
        path = self.cstr(path_ptr)
        data = open(self.hostpath(path), "rb").read()
        info = parse_dylink(data)
        module = Module(data)
        # memory: from the main's own allocator, so that its malloc does not hand the same bytes out again
        size = info["memsize"]
        align = 1 << info["memalign"]
        base = self.alloc(max(align, 16), max(size, 1)) if size else 0
        if size:
            self.mem.write(base, bytes(size))  # BSS is zero
        tsize = info["tablesize"]
        tbase = self.table.grow(tsize) if tsize else len(self.table)
        own_exports = {e.name: e for e in Module.exports(module)}
        got_patch = []  # (global, kind, name)
        env = {}
        for imp in Module.imports(module):
            m, n = imp.module, imp.name
            if m == "env" and imp.kind == "memory":
                env.setdefault("env", {})[n] = self.mem
            elif m == "env" and imp.kind == "table":
                env.setdefault("env", {})[n] = self.table
            elif m == "env" and n == "__memory_base":
                env.setdefault("env", {})[n] = base
            elif m == "env" and n == "__table_base":
                env.setdefault("env", {})[n] = tbase
            elif m == "env" and n == "__stack_pointer":
                env.setdefault("env", {})[n] = self.main_export("__stack_pointer")
            elif m == "env" and imp.kind == "function":
                env.setdefault("env", {})[n] = self.libc_fallback(n)
            elif m in ("GOT.mem", "GOT.func"):
                g = Global("i32", 0, mutable=True)
                if n in own_exports:
                    got_patch.append((g, m, n))  # own symbol: patched after instantiation
                elif m == "GOT.mem":
                    g.value = self.main_export(n).value  # address of a data symbol of the main
                else:
                    g.value = self.slot(self.main_export(n))  # a function of the main -> table slot
                env.setdefault(m, {})[n] = g
            else:
                raise RuntimeError(f"unresolved import {m}.{n}")
        inst = Instance(module, env)
        ex = inst.exports
        for g, m, n in got_patch:
            if m == "GOT.mem":
                g.value = base + ex[n].value
            else:
                g.value = self.slot(ex[n])
        if "__wasm_apply_data_relocs" in own_exports:
            ex["__wasm_apply_data_relocs"]()
        if "__wasm_call_ctors" in own_exports:
            ex["__wasm_call_ctors"]()
        h = self.next
        self.next += 1
        self.libs[h] = dict(instance=inst, base=base, tbase=tbase, info=info)
        self.log.append(
            f"dlopen({path}) -> handle {h}: memory_base={base} (size {size}, align {align}), "
            f"table_base={tbase} (size {tsize}), GOT patched: {[(m, n) for _, m, n in got_patch]}"
        )
        return h

    def dl_sym(self, handle, name_ptr):
        name = self.cstr(name_ptr)
        lib = self.libs[handle]
        try:
            e = lib["instance"].exports[name]
        except KeyError:
            return 0  # no such symbol: dlsym answers NULL (CPython 3.15 asks for PyModExport_<name> first)
        if isinstance(e, Global):
            return lib["base"] + e.value
        return self.slot(e)


def run(wasm, libdir, args=("main",)):
    out = []
    loader = Loader(libdir)
    wasi = Preview1(args=list(args), stdout=lambda b: out.append(bytes(b)))
    imports = wasi.imports()
    imports["env"] = {"dl_open": loader.dl_open, "dl_sym": loader.dl_sym}
    module = Module(open(wasm, "rb").read())
    inst = Instance(module, imports)
    wasi.bind(inst)
    loader.attach(inst)
    code = wasi.start(inst)
    return code, b"".join(out).decode(), loader


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    be = wasmhost.get_backend()
    print(
        "backend:",
        be.name,
        {
            f: be.supports(f)
            for f in ("imports", "import.memory", "import.table", "import.global", "table.funcs", "memory.view")
        },
    )
    code, text, loader = run(os.path.join(here, "main.wasm"), here)
    print(text, end="")
    print("exit code", code)
    for entry in loader.log:
        print(entry)
