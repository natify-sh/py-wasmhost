# ruff: noqa
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import host, wasmhost

for b in ["wasmtime", "node", "bun", "wasm3"]:
    try:
        m = wasmhost.Module(open(os.path.join(host.HERE, "dup.wasm"), "rb").read(), backend=b)
        print(b, "imports:", [(d.module, d.name) for d in wasmhost.Module.imports(m)])
        calls = []
        i = wasmhost.Instance(m, {"wasi:cli/exit@0.2.6": {"exit": lambda c: calls.append(c)}})
        i.exports.a()
        i.exports.b()
        print(b, "OK, one callable served both:", calls)
    except BaseException as e:
        print(b, "FAIL", type(e).__name__, str(e)[:200])
