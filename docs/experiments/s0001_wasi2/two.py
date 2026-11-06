# ruff: noqa
"""Two memories: which comp does a flat import belong to? Run like host.py."""

import os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import host, wasmhost


def run(backend):
    data = open(os.path.join(host.HERE, "two.wasm"), "rb").read()
    p = host.P2(lambda b: None, env=[("A", "1")])
    mod = wasmhost.Module(data, backend=backend)
    out = {}
    # the same (module, name) is imported once: comp is fixed per import object entry, not per caller
    inst = wasmhost.Instance(mod, p.imports(mod))
    p.bind(inst, mems=("memory", "memory$1"), reallocs=("cabi_realloc", "cabi_realloc$1"))
    m0, m1 = inst.exports.memory, inst.exports["memory$1"]
    inst.exports.env0()
    out["after comp-0 call: mem0 ptr/len"] = struct.unpack("<II", m0.read(112, 8))
    out["mem1"] = struct.unpack("<II", m1.read(112, 8))
    # comp 1: another import object whose entries use comp=1
    p2 = host.P2(lambda b: None, env=[("A", "1")])
    inst2 = wasmhost.Instance(mod, p2.imports(mod, comp_of=lambda m, n: 1))
    p2.bind(inst2, mems=("memory", "memory$1"), reallocs=("cabi_realloc", "cabi_realloc$1"))
    inst2.exports.env1()
    m0, m1 = inst2.exports.memory, inst2.exports["memory$1"]
    out["comp=1 call: mem0"] = struct.unpack("<II", m0.read(112, 8))
    out["mem1"] = struct.unpack("<II", m1.read(112, 8))
    return out


for b in sys.argv[1:] or ["wasmtime", "node", "bun", "wasm3"]:
    try:
        print(b, run(b))
    except BaseException as e:
        print(b, "FAIL", type(e).__name__, str(e)[:300])
