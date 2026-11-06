"""`for_module`: the WASI host that fits a module (S0005)."""

from __future__ import annotations

from typing import Any

from ._flavor import wasi_flavor
from .preview1 import Preview1
from .preview2 import Preview2

_ONLY_PREVIEW2 = (
    "network",
    "socket_addr_check",
    "allow_ip_name_lookup",
    "http",
    "http_check",
    "http_send",
    "import_map",
    "memories",
    "reallocs",
)


def for_module(wasm: bytes | bytearray, **options: Any) -> Preview1 | Preview2:
    """`Preview1(**options)` for a module of WASI 0.1 (or with no WASI import),
    `Preview2(**options)` for one of WASI 0.2,
    chosen from the imports in the bytes. A component, a module of WASI 0.3 and bytes that are no module are a
    `ValueError`, and so is an option only `Preview2` has (`network`, `http`, `import_map`...) for a module of 0.1."""
    flavor = wasi_flavor(bytes(wasm))
    if flavor == "component":
        raise ValueError(
            "this is a component, not a core module: make a core module of it first "
            "(`wasm-tools component unbundle`, or `meld fuse` for several components)"
        )
    if flavor == "core-0.3":
        raise ValueError("WASI 0.3 is not supported")
    if flavor == "unknown":
        raise ValueError("not a WebAssembly core module")
    if flavor == "core-0.2":
        return Preview2(**options)
    for name in _ONLY_PREVIEW2:
        if name in options:
            raise ValueError(f"`{name}` is an option of WASI 0.2, and this module is not")
    return Preview1(**options)
