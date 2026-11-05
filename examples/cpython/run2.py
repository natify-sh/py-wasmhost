"""Runs the official CPython (3.15, `wasm32-wasip2`, built from python/cpython with wasi-sdk 34) on
`wasmhost.wasi.Preview2`: the same folder as `run.py`, the WASI 0.2 interface instead of 0.1. `python2.wasm` is the one
core module of the component that CPython's own build makes (`build_wasip2.sh`); its standard library is
`lib/python315.zip`, the one of `run.py` (the same commit). This folder is `/py` to the program, the current folder `/`.

    python examples/cpython/run2.py -c "print(1 + 1)"
    python examples/cpython/run2.py script.py                        # a file in the current folder
    python examples/cpython/run2.py --dir ~/data:/data -c "print(open('/data/a.txt').read())"
    python examples/cpython/run2.py -S inherit-network,allow-ip-name-lookup -c "..."   # the flags of `wasmhost run -S`

The exit code of the program is only `0` or `1`: the export `wasi:cli/run#run` of the component returns ok or err, and
CPython's `main` returns its code (`sys.exit(3)` is 3) which that export turns into err for any value but 0. So
`sys.exit(3)` gives 1 here. It is the interface, not a defect of wasmhost.

What is not checked: sockets and TLS (`-S` is passed on, nothing more), `pip`, stdin, another CPython commit, and the
backends other than wasmtime, wasm3 and Node for the program itself.
"""

import os
import sys

from wasmhost import Module
from wasmhost.wasi import Preview2
from wasmhost.wasi._flavor import network_options

HERE = os.path.dirname(os.path.abspath(__file__))


def main(argv):
    preopens = {"/": os.getcwd(), "/py": HERE}  # the program starts in `/`, so that is the current folder
    flags = []
    while argv[:1] in (["--dir"], ["-S"]) and len(argv) > 1:
        if argv[0] == "--dir":  # --dir HOST[:GUEST], the guest name defaults to the host path
            host, _, guest = argv[1].partition(":")
            preopens[guest or host] = os.path.expanduser(host)
        else:
            flags.append(argv[1])
        argv = argv[2:]
    with open(os.path.join(HERE, "python2.wasm"), "rb") as file:
        module = Module(file.read())
    stdout, stderr = sys.stdout.buffer.write, sys.stderr.buffer.write
    env = {"PYTHONHOME": "/py"}
    wasi = Preview2(
        ["/py/python.wasm", *argv], env, preopens, sys.stdin.buffer, stdout, stderr, **network_options(flags)
    )
    return wasi.run(module)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
