"""Runs python3.wasm (CPython with dlopen as an import of the host) through Preview2, with the loader of dl_loader_cpy."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dl_loader_cpy as dl

import wasmhost
from wasmhost import Instance, Module
from wasmhost.wasi import Preview2

MODULE = os.environ.get("PY3", "python3.wasm")
CPY = "/home/user/py-wasmhost/examples/cpython"
here = os.path.dirname(os.path.abspath(__file__))
preopens = {"/py": CPY, "/site": os.path.join(here, os.environ.get("SITE", "site")), "/": os.getcwd()}
loader = dl.Loader(preopens)
out = []
wasi = Preview2(
    args=["python3.wasm", *sys.argv[1:]],
    env={"PYTHONHOME": "/py", "PYTHONPATH": "/site"},
    preopens=preopens,
    stdout=lambda b: (sys.stdout.buffer.write(b), sys.stdout.flush()),
    stderr=lambda b: (sys.stderr.buffer.write(b), sys.stderr.flush()),
)


def dlopen(path_ptr, flags):
    try:
        return loader.dl_open(path_ptr)
    except Exception as exc:  # report, answer NULL: CPython raises ImportError
        print("loader error:", type(exc).__name__, exc, file=sys.stderr)
        return 0


module = Module(open(os.path.join(here, MODULE), "rb").read())
imports = wasi.imports(module)
imports["env"] = {"dlopen": dlopen, "dlsym": loader.dl_sym, "dlerror": lambda: 0}
t = time.time()
instance = Instance(module, imports)
wasi.bind(instance)
loader.attach(instance)
code = wasi.start(instance)
print(f"[{wasmhost.get_backend().name} exit {code}, {time.time() - t:.1f}s]", file=sys.stderr)
for line in loader.log:
    print(line, file=sys.stderr)
