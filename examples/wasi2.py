"""WASI 0.2 on `wasmhost.wasi.Preview2`: the core module of a component, run by whatever backend takes imports.

    python examples/wasi2.py hello [--backend NAME]   # runs examples/wasi2/hello.wasm: prints "hello from wasip2"
    python examples/wasi2.py sock [--network]         # a TCP client against a tiny server inside this script

`sock` runs `tests/data/wasi2/_sock.wasm` (a C program built with wasi-sdk): it connects to 127.0.0.1:47123, sends
`ping` and prints the reply. A WASI program has no network of its own, so the host has to allow it: by default the
connection is denied (`connect: Permission denied`, exit code 1); with `--network` it is allowed (`reply: pong`, 0).
The server is bound to 127.0.0.1 only and closed at the end. The exit code of this script is the program's code.

Only the library is built: there is no `wasmhost run` for WASI 0.2 yet, and a component is unbundled first
(see examples/wasi2/README.md).
"""

import os
import socket
import sys
import threading

import wasmhost
from wasmhost import Module
from wasmhost.wasi import Preview2

HERE = os.path.dirname(os.path.abspath(__file__))
SOCK = os.path.join(HERE, "..", "tests", "data", "wasi2", "_sock.wasm")
PORT = 47123


def load(path):
    with open(path, "rb") as file:
        return Module(file.read())


def serve(seen):
    """Answers one client with `pong` on 127.0.0.1 (gives up after a few seconds); returns the thread and the socket."""
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", PORT))
    listener.listen(1)
    listener.settimeout(3)

    def run():
        try:
            conn, _ = listener.accept()
            with conn:
                conn.settimeout(3)
                data = conn.recv(64)
                if data:  # an empty read is the wake-up of `main`, not a client
                    seen.append(data)
                    conn.sendall(b"pong")
        except OSError:
            pass

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, listener


def main(argv):
    backend = None
    if "--backend" in argv:
        i = argv.index("--backend")
        backend = argv[i + 1]
        del argv[i : i + 2]
    if backend:
        wasmhost.set_backend(backend)
    command = argv[0] if argv else ""
    stdout, stderr = sys.stdout.buffer.write, sys.stderr.buffer.write
    if command == "hello":
        code = Preview2(stdout=stdout, stderr=stderr).run(load(os.path.join(HERE, "wasi2", "hello.wasm")))
        print("exit code:", code)
        return code
    if command == "sock":
        if not os.path.exists(SOCK):
            print("skipped: needs tests/data/wasi2/_sock.wasm of the repository")
            return 0
        seen = []
        thread, listener = serve(seen)
        try:
            code = Preview2(network="--network" in argv, stdout=stdout, stderr=stderr).run(load(SOCK))
        finally:
            if thread.is_alive():  # nobody came (denied): wake the accept instead of waiting for its timeout
                with socket.socket() as waker:
                    waker.settimeout(1)
                    try:
                        waker.connect(("127.0.0.1", PORT))
                    except OSError:
                        pass
            listener.close()
            thread.join(5)
        print("exit code:", code, "| the server saw:", seen)
        return code
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
