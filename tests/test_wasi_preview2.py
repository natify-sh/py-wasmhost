"""`wasmhost.wasi.preview2` on every backend that takes host functions: a core module of one WASI 0.2 component."""

from __future__ import annotations

import socket
import struct
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import wasm_builder as wb
from fusedwasi import Exit

import wasmhost
from wasmhost import LinkError, Module
from wasmhost.wasi import Preview1, Preview2

DATA = Path(__file__).parent / "data" / "wasi2"
HELLO = b"hello from wasip2\n"
PORT = 47123
RUN = "wasi:cli/run@0.2.6#run"


@pytest.fixture(autouse=True)
def need_imports(session: str) -> None:
    if not wasmhost.get_backend().supports("imports"):
        pytest.skip(f"the {session} backend can't take imports")


def one(session: str) -> Module:
    return Module((DATA / "one.wasm").read_bytes(), backend=session)


def test_hello_returns_ok(session: str) -> None:
    out: list[bytes] = []
    assert Preview2(stdout=out.append).run(one(session)) == 0
    assert b"".join(out) == HELLO


def test_environment_and_random_bytes(session: str) -> None:
    out: list[bytes] = []
    wasi = Preview2(env={"A": "1", "HOME": "/h"}, stdout=out.append)
    instance = wasi.instantiate(one(session))
    assert wasi.start(instance) == 0
    mem = instance.exports.memory

    def random_bytes() -> bytes:
        ptr, length = struct.unpack("<II", mem.read(96, 8))
        return mem.read(ptr, length)

    first = random_bytes()
    ptr, n = struct.unpack("<II", mem.read(112, 8))
    pairs = [struct.unpack("<IIII", mem.read(ptr + 16 * i, 16)) for i in range(n)]
    assert [(mem.read(a, b), mem.read(c, d)) for a, b, c, d in pairs] == [(b"A", b"1"), (b"HOME", b"/h")]
    assert len(first) == 8
    wasi.start(instance)  # a second run of the same instance: other random bytes
    assert random_bytes() != first


def test_exit_gives_its_code(session: str) -> None:
    wasi = Preview2(stdout=lambda data: None)
    instance = wasi.instantiate(one(session))
    with pytest.raises(Exception, match="1") as caught:
        exit1: Any = instance.exports["exit1"]
        exit1()
    assert type(caught.value).__name__ == "Exit"
    assert wasi.start(instance) == 0


def test_exit_in_run_is_the_exit_code() -> None:
    """`start` turns the `Exit` of `wasi:cli/exit` into its code (an instance is faked: only its exports are used)."""

    def run() -> int:
        raise Exit(7)

    class Fake:
        exports = {"memory": object(), "cabi_realloc": print, RUN: run}

    assert Preview2().start(Fake()) == 7  # type: ignore[arg-type]


def test_a_module_without_the_run_export(session: str) -> None:
    data = (DATA / "one.wasm").read_bytes().replace(RUN.encode(), b"wasi:cli/run@0.2.6#xxx")
    with pytest.raises(TypeError, match="run@0.2.N#run"):
        Preview2().run(Module(data, backend=session))


def test_a_module_of_wasi_03_is_a_link_error(session: str) -> None:
    data = (DATA / "one.wasm").read_bytes().replace(b"wasi:cli/exit@0.2.6", b"wasi:cli/exit@0.3.0")
    with pytest.raises(LinkError, match="wasi:cli/exit@0.3.0"):
        Preview2().imports(Module(data, backend=session))


def test_a_component_is_refused_by_module(session: str) -> None:
    component = b"\x00asm\x0d\x00\x01\x00"
    with pytest.raises(wasmhost.CompileError):
        Module(component, backend=session)


def test_a_state_given_takes_no_other_option() -> None:
    state = Preview1().state
    with pytest.raises(TypeError, match="state="):
        Preview2(state=state, args=["x"])
    with pytest.raises(TypeError, match="state="):
        Preview2(state=state, network=True)
    with pytest.raises(TypeError, match="state="):
        Preview1(state=state, env={"A": "1"})


def test_the_state_is_shared_and_its_owner_closes_it(session: str, tmp_path: Path) -> None:
    out: list[bytes] = []
    p1 = Preview1(args=["prog", "x"], env={"A": "1"}, preopens={"/": tmp_path}, stdout=out.append)
    instance = p1.instantiate(Module(wb.wasi_hello(), backend=session))
    assert p1.start(instance) == 2  # makes note.txt through the 0.1 calls
    assert (tmp_path / "note.txt").exists()
    p2 = Preview2(state=p1.state)
    assert p2.state is p1.state and Preview1(state=p1.state).state is p1.state
    out.clear()
    assert p2.run(one(session)) == 0  # the stdout of p1 is the stdout of p2
    assert out == [HELLO]
    p2.close()  # a State that was given is not closed by the one that was given it: p1 still writes
    assert p1.start(instance) == 2 and out == [HELLO, b"hello, wasi\n"]
    p1.close()


def test_the_environment_of_preview1_is_what_preview2_reads(session: str) -> None:
    p1 = Preview1(args=["prog"], env={"K": "v"}, stdout=lambda data: None)
    wasi = Preview2(state=p1.state)
    instance = wasi.instantiate(one(session))
    assert wasi.start(instance) == 0
    mem = instance.exports.memory
    ptr, n = struct.unpack("<II", mem.read(112, 8))
    a, b, c, d = struct.unpack("<IIII", mem.read(ptr, 16))
    assert n == 1 and (mem.read(a, b), mem.read(c, d)) == (b"K", b"v")


# --- sockets: wasmext's `_sock.wasm` connects to 127.0.0.1:47123, sends `ping`, prints `reply: <answer>`


@pytest.fixture
def server() -> Iterator[list[bytes]]:
    seen: list[bytes] = []
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # the port of the last test may be in TIME_WAIT
    try:
        listener.bind(("127.0.0.1", PORT))
    except OSError as caught:
        listener.close()
        pytest.skip(f"port {PORT} is busy: {caught}")
    listener.listen(1)
    listener.settimeout(5)

    def serve() -> None:
        try:
            conn, _ = listener.accept()
            with conn:
                conn.settimeout(5)
                seen.append(conn.recv(64))
                conn.sendall(b"pong")
        except OSError:
            pass  # nobody came (the network was denied): the test checks `seen`

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield seen
    if thread.is_alive():  # nobody came (denied): wake the accept instead of waiting for its timeout
        with socket.socket() as waker:
            waker.settimeout(1)
            try:
                waker.connect(("127.0.0.1", PORT))
            except OSError:
                pass
    listener.close()
    thread.join(7)


def sock(session: str) -> Module:
    return Module((DATA / "_sock.wasm").read_bytes(), backend=session)


def test_network_opened(session: str, server: list[bytes]) -> None:
    out: list[bytes] = []
    assert Preview2(network=True, stdout=out.append).run(sock(session)) == 0
    assert b"".join(out) == b"reply: pong\n"
    assert server == [b"ping"]


def test_network_denied_by_default(session: str, server: list[bytes]) -> None:
    out: list[bytes] = []
    assert Preview2(stdout=out.append, stderr=out.append).run(sock(session)) == 1
    assert b"".join(out) == b"connect: Permission denied\n"
    assert server == []


def test_a_check_that_allows_only_that_port(session: str, server: list[bytes]) -> None:
    out: list[bytes] = []
    asked: list[tuple[str, int, int]] = []

    def check(ip: str, port: int, use: int) -> bool:
        asked.append((ip, port, use))
        return ip == "127.0.0.1" and port == PORT

    assert Preview2(socket_addr_check=check, stdout=out.append).run(sock(session)) == 0
    assert b"".join(out) == b"reply: pong\n" and asked == [("127.0.0.1", PORT, 1)]


def test_a_check_that_denies_is_the_default(session: str, server: list[bytes]) -> None:
    out: list[bytes] = []
    assert (
        Preview2(socket_addr_check=lambda ip, port, use: False, stdout=out.append, stderr=out.append).run(sock(session))
        == 1
    )
    assert b"".join(out) == b"connect: Permission denied\n" and server == []
