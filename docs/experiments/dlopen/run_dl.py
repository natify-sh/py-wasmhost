import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dl_loader

import wasmhost
from wasmhost import Instance, Module
from wasmhost.wasi.preview1 import Preview1

here = os.path.dirname(os.path.abspath(__file__))
name = sys.argv[1]
mode = sys.argv[2]
out = []
L = dl_loader.Loader(here)
err = [0]
wasi = Preview1(args=["m"], stdout=lambda b: out.append(bytes(b)))
imp = wasi.imports()
if mode == "host":

    def dlerror():
        return 0

    def dlopen(p, flags):
        try:
            return L.dl_open(p)
        except Exception as e:
            print("loader error:", type(e).__name__, e)
            return 0

    imp["env"] = {"dlopen": dlopen, "dlsym": L.dl_sym, "dlerror": dlerror}
inst = Instance(Module(open(os.path.join(here, name), "rb").read()), imp)
wasi.bind(inst)
L.attach(inst)
code = wasi.start(inst)
print(wasmhost.get_backend().name, name, "exit", code, repr(b"".join(out).decode()))
