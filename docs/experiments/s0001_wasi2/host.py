# ruff: noqa
"""Prototype: WASI 0.2 flat imports through wasmhost over one fusedwasi State.
Run: cd /home/user/py-wasmhost && PYTHONPATH=<fw-b1> uv run --no-sync python $S/host.py [backend ...]"""

import struct, sys, os
import fusedwasi
from fusedwasi import Exit, Guest, State, signatures
from fusedwasi.p2 import InputStream, OutputStream
import wasmhost

HERE = os.path.dirname(os.path.abspath(__file__))
M32, M64 = 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF


class Out(OutputStream):
    def __init__(self, sink):
        self.sink = sink

    def check_write(self):
        return 4096

    def write(self, data):
        self.sink(data)


class P2:
    """One State; imports() builds the import object for the module's wasi:* imports; bind(instance, ...) gives memories+realloc."""

    def __init__(self, stdout, env=()):
        self.state = State(args=["prog"], env=list(env), stdout=Out(stdout), stderr=Out(lambda b: None))
        self.memories = []  # filled by bind (instance memory only exists after instantiation)
        self.reallocs = []  # cabi_realloc callables per comp
        self.guest = Guest(self.state, [self._mem(i) for i in range(8)], realloc=self._realloc)
        self.guest_exit = None

    def _mem(self, i):  # a callable per comp: the Guest asks at call time, so late binding works
        return lambda: self.memories[i] if i < len(self.memories) else None

    def _realloc(self, comp, old, osz, align, nsz):
        return self.reallocs[comp](old, osz, align, nsz)

    def imports(self, module, comp_of=lambda module, name: 0):
        out = {}
        for d in wasmhost.Module.imports(module):
            if d.kind != "function" or not d.module.startswith("wasi:"):
                continue
            row = signatures.find_import(d.module, d.name)
            if row is None:
                raise wasmhost.LinkError(f"no fusedwasi function for {d.module} {d.name}")
            fn = row.python_function()
            masks = tuple(M64 if p.type == "i64" else M32 for p in row.params)
            comp = comp_of(d.module, d.name)

            def call(*a, fn=fn, masks=masks, comp=comp, takes=row.takes_comp, rets=bool(row.results)):
                a = [x & m for x, m in zip(a, masks)]
                r = fn(self.guest, comp, *a) if takes else fn(self.guest, *a)
                return r if rets else None

            out.setdefault(d.module, {})[d.name] = call
        return out

    def bind(self, inst, mems=("memory",), reallocs=("cabi_realloc",)):
        self.memories = [getattr(inst.exports, n) for n in mems]
        self.reallocs = [getattr(inst.exports, n) for n in reallocs]


def run(backend, wasm="one.wasm"):
    data = open(os.path.join(HERE, wasm), "rb").read()
    got = bytearray()
    p = P2(got.extend, env=[("A", "1"), ("HOME", "/h")])
    mod = wasmhost.Module(data, backend=backend)
    inst = wasmhost.Instance(mod, p.imports(mod))
    p.bind(inst)
    rc = inst.exports["wasi:cli/run@0.2.6#run"]()
    mem = inst.exports.memory
    rp, rl = struct.unpack("<II", mem.read(96, 8))
    rnd = mem.read(rp, rl)
    ptr, n = struct.unpack("<II", mem.read(112, 8))
    envs = [struct.unpack("<IIII", mem.read(ptr + 16 * i, 16)) for i in range(n)]
    envs = [(mem.read(a, b), mem.read(c, d)) for a, b, c, d in envs]
    exit_msg = None
    try:
        inst.exports["exit1"]()
    except BaseException as e:
        exit_msg = f"{type(e).__module__}.{type(e).__name__}: {e}"
    return rc, bytes(got), rnd.hex(), envs, exit_msg


if __name__ == "__main__":
    print("fusedwasi", fusedwasi.__version__)
    for b in sys.argv[1:] or ["wasmtime", "node", "bun", "wasm3"]:
        try:
            print(b, "OK", run(b))
        except BaseException as e:
            print(b, "FAIL", type(e).__name__, str(e)[:300])
