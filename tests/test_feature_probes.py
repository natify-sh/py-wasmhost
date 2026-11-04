"""What the backend takes of WebAssembly, measured where CI runs it: one line in the log (`WASMHOST-SUPPORTS {...}`),
which `tools/probe_features.py --collect` turns into SUPPORTS.md.

Nothing here fails on a feature an engine lacks (that is the finding); the test fails only if the baseline module
(`mvp`) does not run, since then nothing else means anything."""

from __future__ import annotations

import importlib.metadata as md
import json
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import wasm_builder as wb
from feature_probes import run

import wasmhost
from wasmhost.wasi import preview1


def _engine(name: str) -> str:
    """The version of the engine behind a backend, as far as it can be told from here; "?" when it can not."""

    def dist(package: str) -> str:
        try:
            return md.version(package)
        except md.PackageNotFoundError:
            return "?"

    def out(cmd: list[str]) -> str:
        try:
            return (
                subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=20).stdout.strip().lstrip("v")
                or "?"
            )
        except (OSError, subprocess.SubprocessError):
            return "?"

    if name == "wasmtime":
        return f"wasmtime-py {dist('wasmtime')}"
    if name == "wasm3":
        return f"pywasm3 {dist('pywasm3')}"
    if name == "node":
        return f"node {out(['node', '--version'])}"
    if name == "bun":
        return f"bun {out(['bun', '--version'])}"
    if name == "pyodide":
        return f"pyodide {getattr(sys.modules.get('pyodide'), '__version__', '?')}"
    return "?"


def _wasi(backend: str) -> str:
    out: list[bytes] = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            code = preview1.Preview1(args=["p", "a"], preopens={"/": Path(tmp)}, stdout=out.append).run(
                wasmhost.Module(wb.wasi_hello(), backend=backend)
            )
        return "yes" if code == 2 and b"".join(out) == b"hello, wasi\n" else "no"
    except BaseException:  # noqa: BLE001 -- a backend that can not take host functions answers "no"
        return "no"


def test_what_the_backend_takes(session: str, capsys: pytest.CaptureFixture[str]) -> None:
    backend = session
    features = run(backend)
    record = {
        "backend": backend,
        "engine": _engine(backend),
        "os": platform.system(),
        "python": f"{platform.python_implementation()} {platform.python_version()}",
        "api": sorted(
            wasmhost.get_backend().features
        ),  # the live backend: some add strings when the engine starts (`imports`)
        "wasi": _wasi(backend),
        "features": features,
    }
    with capsys.disabled():  # into the log of CI whatever -q, -v or -s say
        print("WASMHOST-SUPPORTS " + json.dumps(record, sort_keys=True), flush=True)
    assert features["mvp"] == "yes"
