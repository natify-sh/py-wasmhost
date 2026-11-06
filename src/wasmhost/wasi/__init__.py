"""WASI hosts, one module for each version of the interface: `preview1` is WASI 0.1 (`wasi_snapshot_preview1`, and
the first snapshot, `wasi_unstable`); `preview2` is WASI 0.2 for a core module of one component (`Preview2`).

    from wasmhost.wasi import Preview1                  # the host of WASI 0.1, as its name says
    from wasmhost.wasi import preview1                # the module: its tables, `SIGNATURES`, `WasiExit`...

A class is exported under a name that says its version (`Preview1`), so one cannot be taken for the other.
"""

from . import preview1, preview2
from .preview1 import Preview1
from .preview2 import Preview2

__all__ = ("Preview1", "Preview2", "preview1", "preview2")
