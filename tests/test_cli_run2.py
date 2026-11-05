"""`wasmhost run` for WASI 0.2 (S0001, step B): the `-S` flags, the telling of the module, the three errors."""

from __future__ import annotations

import socket
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
import wasm_builder as wb
from fusedwasi.p2.wasi_p2_core import USE_TCP_BIND, USE_TCP_CONNECT, USE_UDP_BIND, USE_UDP_CONNECT, USE_UDP_OUTGOING

import wasmhost
from wasmhost import _cli
from wasmhost.wasi._flavor import network_options, wasi_flavor

DATA = Path(__file__).parent / "data" / "wasi2"
PORT = 47123
TCP = (USE_TCP_BIND, USE_TCP_CONNECT)
UDP = (USE_UDP_BIND, USE_UDP_CONNECT, USE_UDP_OUTGOING)


def test_the_flavor_is_read_from_the_bytes() -> None:
    one, sock = (DATA / "one.wasm").read_bytes(), (DATA / "_sock.wasm").read_bytes()
    assert wasi_flavor(b"\0asm\x0d\x00\x01\x00") == "component"
    assert wasi_flavor(one) == wasi_flavor(sock) == "core-0.2"
    assert wasi_flavor(one.replace(b"wasi:cli/exit@0.2.6", b"wasi:cli/exit@0.3.0")) == "core-0.3"
    assert wasi_flavor(wb.wasi_hello()) == "core-0.1"
    assert wasi_flavor(wb.wasi_hello("wasi_unstable")) == "core-0.1"
    assert wasi_flavor(wb.arith()) == "none"
    assert wasi_flavor(b"hello") == wasi_flavor(b"") == "unknown"


def test_no_flag_changes_nothing() -> None:
    assert network_options([]) == {}
    assert network_options(["tcp", "udp", "tcp=y,udp=yes"]) == {}  # the address check decides, as in wasmtime


def test_inherit_network_opens_the_network_but_not_the_lookup() -> None:
    assert network_options(["inherit-network"]) == {"network": True, "allow_ip_name_lookup": False}
    both = {"network": True, "allow_ip_name_lookup": True}
    assert network_options(["inherit-network,allow-ip-name-lookup"]) == both
    assert network_options(["allow-ip-name-lookup", "inherit-network"]) == both  # the order does not matter
    assert network_options(["inherit-network=n"]) == {}
    assert network_options(["allow-ip-name-lookup=n"]) == {"allow_ip_name_lookup": False}
    assert network_options(["inherit-network=on", "allow-ip-name-lookup=off"]) == {
        "network": True,
        "allow_ip_name_lookup": False,
    }


@pytest.mark.parametrize("word", ["y", "yes", "true", "on", "1"])
def test_yes_values(word: str) -> None:
    assert network_options([f"inherit-network={word}"])["network"] is True


@pytest.mark.parametrize("word", ["n", "no", "false", "off", "0", "NO"])
def test_no_values(word: str) -> None:
    assert "network" not in network_options([f"inherit-network={word}"])


def test_tcp_and_udp_off_become_an_address_check() -> None:
    check = network_options(["inherit-network,tcp=n"])["socket_addr_check"]
    assert [check("1.2.3.4", 1, use) for use in TCP] == [False, False]
    assert all(check("1.2.3.4", 1, use) for use in UDP)
    check = network_options(["inherit-network", "udp=no"])["socket_addr_check"]
    assert [check("1.2.3.4", 1, use) for use in UDP] == [False] * 3
    assert all(check("1.2.3.4", 1, use) for use in TCP)
    check = network_options(["tcp=n,inherit-network,udp=n"])["socket_addr_check"]  # tcp=n before it: still applied last
    assert not any(check("1.2.3.4", 1, use) for use in TCP + UDP)
    assert network_options(["tcp=n"]) == {}  # without inherit-network nothing is open: nothing to close


def test_an_unknown_key_is_named() -> None:
    for word in ("http", "inherit-networks"):
        with pytest.raises(ValueError, match=f"`{word}`.*inherit-network, allow-ip-name-lookup, tcp, udp"):
            network_options([f"inherit-network,{word}"])
    with pytest.raises(ValueError, match="not a yes or a no"):
        network_options(["tcp=maybe"])


@pytest.fixture
def need_imports(session: str) -> None:
    if not wasmhost.get_backend(session).supports("imports"):
        pytest.skip(f"the {session} backend can't take imports")


def run(session: str, *line: str) -> int:
    return _cli.main(["run", "--backend", session, *line])


def test_hello_of_wasi_02(capsys: pytest.CaptureFixture[str], session: str, need_imports: None) -> None:
    assert run(session, str(DATA / "one.wasm")) == 0
    assert capsys.readouterr().out == "hello from wasip2\n"
    assert run(session, "-S", "inherit-network", str(DATA / "one.wasm")) == 0  # a flag the module does not use


@pytest.fixture
def server() -> Iterator[list[bytes]]:
    if sys.platform == "emscripten":
        pytest.skip("Python in Pyodide has no sockets")
    seen: list[bytes] = []
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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
            pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield seen
    if thread.is_alive():
        with socket.socket() as waker:
            waker.settimeout(1)
            try:
                waker.connect(("127.0.0.1", PORT))
            except OSError:
                pass
    listener.close()
    thread.join(7)


def test_the_network_is_denied_without_a_flag(
    capsys: pytest.CaptureFixture[str], session: str, need_imports: None, server: list[bytes]
) -> None:
    assert run(session, str(DATA / "_sock.wasm")) == 1
    assert capsys.readouterr().err == "connect: Permission denied\n"  # perror: the standard error
    assert server == []


def test_inherit_network_opens_it(
    capsys: pytest.CaptureFixture[str], session: str, need_imports: None, server: list[bytes]
) -> None:
    assert run(session, "-S", "inherit-network", str(DATA / "_sock.wasm")) == 0
    assert capsys.readouterr().out == "reply: pong\n"
    assert server == [b"ping"]


def test_tcp_off_closes_it_again(
    capsys: pytest.CaptureFixture[str], session: str, need_imports: None, server: list[bytes]
) -> None:
    assert run(session, "-S", "inherit-network,tcp=n", str(DATA / "_sock.wasm")) == 1
    assert capsys.readouterr().err == "connect: Permission denied\n"  # perror: the standard error
    assert server == []


def test_a_component_is_refused(capsys: pytest.CaptureFixture[str], session: str, tmp_path: Path) -> None:
    path = tmp_path / "c.wasm"
    path.write_bytes(b"\0asm\x0d\x00\x01\x00")
    assert run(session, str(path)) == 1
    err = capsys.readouterr().err
    assert "component" in err and "unbundle" in err and "meld fuse" in err


def test_wasi_03_is_refused(capsys: pytest.CaptureFixture[str], session: str, tmp_path: Path) -> None:
    path = tmp_path / "m.wasm"
    path.write_bytes((DATA / "one.wasm").read_bytes().replace(b"wasi:cli/exit@0.2.6", b"wasi:cli/exit@0.3.0"))
    assert run(session, str(path)) == 1
    assert "WASI 0.3 is not supported" in capsys.readouterr().err


def test_network_flags_on_a_wasi_01_module_are_an_error(
    capsys: pytest.CaptureFixture[str], session: str, tmp_path: Path
) -> None:
    path = tmp_path / "hello.wasm"
    path.write_bytes(wb.wasi_hello())
    assert run(session, "-S", "inherit-network", str(path)) == 1
    assert "the network flags are for modules of WASI 0.2" in capsys.readouterr().err


def test_an_unknown_flag_is_an_error(capsys: pytest.CaptureFixture[str], session: str) -> None:
    assert run(session, "-S", "http", str(DATA / "one.wasm")) == 1
    assert "unknown -S flag `http`" in capsys.readouterr().err
