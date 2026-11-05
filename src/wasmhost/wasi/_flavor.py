"""What `wasmhost run` reads from the bytes and the `-S` words before it runs a module (S0001, step B)."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import Any

from fusedwasi.p2.wasi_p2_core import USE_TCP_BIND, USE_TCP_CONNECT, USE_UDP_BIND, USE_UDP_CONNECT, USE_UDP_OUTGOING

from .._binary import parse

_WASI_VERSION = re.compile(r"wasi:.+@0\.(\d+)\.\d+")
_TCP_USES = frozenset({USE_TCP_BIND, USE_TCP_CONNECT})
_UDP_USES = frozenset({USE_UDP_BIND, USE_UDP_CONNECT, USE_UDP_OUTGOING})
_YES = frozenset({"y", "yes", "true", "on", "1"})
_NO = frozenset({"n", "no", "false", "off", "0"})
KEYS = ("inherit-network", "allow-ip-name-lookup", "tcp", "udp")


def wasi_flavor(data: bytes) -> str:
    """`component`, `core-0.1`, `core-0.2`, `core-0.3`, `none` (no WASI import) or `unknown` (not a module), read from
    the bytes alone; the newest WASI the imports ask for wins."""
    if data[:4] == b"\0asm" and data[4:8] == b"\x0d\x00\x01\x00":
        return "component"
    try:
        modules = {d.module for d in parse(data).imports}
    except ValueError:
        return "unknown"
    found: set[str] = {"core-0.1"} if modules & {"wasi_snapshot_preview1", "wasi_unstable"} else set()
    for name in modules:
        match = _WASI_VERSION.fullmatch(name)
        if match and match.group(1) in ("2", "3"):
            found.add(f"core-0.{match.group(1)}")
    return max(found) if found else "none"


def _flag(key: str, value: str | None) -> bool:
    if value is None or value.lower() in _YES:
        return True
    if value.lower() in _NO:
        return False
    raise ValueError(f"-S {key}: `{value}` is not a yes or a no (y, yes, true, on, 1, n, no, false, off, 0)")


def network_options(flags: Sequence[str]) -> dict[str, Any]:
    """The keyword arguments of `Preview2` for the words of the `-S` options (each a comma-separated list of
    `KEY[=VALUE]`), as Wasmtime reads them: empty when there is no flag. Raises ValueError for an unknown key."""
    given: dict[str, bool] = {}
    for item in flags:
        for word in item.split(","):
            key, has_value, value = word.strip().partition("=")
            if not key:
                continue
            if key not in KEYS:
                raise ValueError(f"unknown -S flag `{key}` (the flags that exist: {', '.join(KEYS)})")
            given[key] = _flag(key, value if has_value else None)
    options: dict[str, Any] = {}
    if given.get("inherit-network"):
        options["network"] = True
        options["allow_ip_name_lookup"] = False  # as Wasmtime: the lookup is a flag of its own
    if "allow-ip-name-lookup" in given:
        options["allow_ip_name_lookup"] = given["allow-ip-name-lookup"]
    refused: frozenset[int] = frozenset()
    if given.get("tcp") is False:
        refused |= _TCP_USES
    if given.get("udp") is False:
        refused |= _UDP_USES
    if refused and options.get("network"):
        check: Callable[[str, int, int], bool] = lambda ip, port, use: use not in refused  # noqa: E731
        options["socket_addr_check"] = check
    return options
