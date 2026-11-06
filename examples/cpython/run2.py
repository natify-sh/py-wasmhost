"""Runs the official CPython (3.15, `wasm32-wasip2`, built from python/cpython with wasi-sdk 34) on
`wasmhost.wasi.Preview2`: the same folder as `run.py`, the WASI 0.2 interface instead of 0.1. `python2.wasm` is the one
core module of the component that CPython's own build makes (`build_wasip2.sh`); its standard library is
`lib/python315.zip`, the one of `run.py` (the same commit). This folder is `/py` to the program, the current folder `/`.

    python examples/cpython/run2.py -c "print(1 + 1)"
    python examples/cpython/run2.py script.py                        # a file in the current folder
    python examples/cpython/run2.py --dir ~/data:/data -c "print(open('/data/a.txt').read())"
    python examples/cpython/run2.py --env NAME=VALUE -c "import os; print(os.environ['NAME'])"
    python examples/cpython/run2.py -S inherit-network=n,allow-ip-name-lookup=n -c "..."
    python examples/cpython/run2.py --module python2_ssl.wasm -c "import ssl; print(ssl.OPENSSL_VERSION)"

The network is open by default here (see `main`); the `-S` line above, the flags of `wasmhost run -S`, closes it.
pip is not in the standard library zip: put a wheel of it on the path, and give it a HOME:
`--dir wheels:/w --env HOME=/w --env PYTHONPATH=/w/pip.whl -m pip --version`.

The exit code of the program is only `0` or `1`: the export `wasi:cli/run#run` of the component returns ok or err, and
CPython's `main` returns its code (`sys.exit(3)` is 3) which that export turns into err for any value but 0. So
`sys.exit(3)` gives 1 here. It is the interface, not a defect of wasmhost.

What was run by hand (wasmtime, Linux): `pip install --no-cache-dir` of a pure-Python wheel from a folder
(`--no-index --find-links`) and from a plain-http index of a local `http.server` on 127.0.0.1. Without
`--no-cache-dir` pip 26.3 stops with `AttributeError: module 'mmap' has no attribute 'ACCESS_READ'`: the `mmap`
of this build is the stub of `sitecustomize`.

The build of `python2.wasm` has no `ssl` (`_ssl` is not built). `build_wasip2_ssl.sh` builds `python2_ssl.wasm` with
OpenSSL 3.5.0 (`--module`), with which `get-pip.py` and `pip install --no-cache-dir --cert ...` over https to a local
server worked, by hand on wasmtime and Node, not in CI. WASI has no default CA store: give `cafile` or `--cert`.

What is not checked: stdin, another CPython commit, and the backends other than wasmtime, wasm3 and Node for the
program itself.
"""

import os
import sys

from wasmhost import Module
from wasmhost.wasi import Preview2
from wasmhost.wasi._flavor import network_options

HERE = os.path.dirname(os.path.abspath(__file__))


def main(argv):
    preopens = {"/": os.getcwd(), "/py": HERE}  # the program starts in `/`, so that is the current folder
    # The network is open here, unlike in `wasmhost run` and in the library (where it is denied unless asked for):
    # the point of this program is to reach the index of pip and the like. A `-S` flag of the command line comes
    # later and wins: `-S inherit-network=n,allow-ip-name-lookup=n` closes it.
    flags = ["inherit-network", "allow-ip-name-lookup"]
    env = {"PYTHONHOME": "/py"}
    module_path = os.path.join(HERE, "python2.wasm")
    while argv[:1] in (["--dir"], ["-S"], ["--env"], ["--module"]) and len(argv) > 1:
        if argv[0] == "--dir":  # --dir HOST[:GUEST], the guest name defaults to the host path
            host, _, guest = argv[1].partition(":")
            preopens[guest or host] = os.path.expanduser(host)
        elif (
            argv[0] == "--module"
        ):  # --module PATH: another build of CPython, for example python2_ssl.wasm of build_wasip2_ssl.sh
            module_path = os.path.expanduser(argv[1])
        elif argv[0] == "--env":  # --env NAME=VALUE (pip wants HOME)
            name, _, value = argv[1].partition("=")
            env[name] = value
        else:
            flags.append(argv[1])
        argv = argv[2:]
    with open(module_path, "rb") as file:
        module = Module(file.read())
    stdout, stderr = sys.stdout.buffer.write, sys.stderr.buffer.write
    wasi = Preview2(
        ["/py/python.wasm", *argv], env, preopens, sys.stdin.buffer, stdout, stderr, **network_options(flags)
    )
    return wasi.run(module)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
