# Pyodide without JavaScript: moved

The experiment (Pyodide's `pyodide.asm.wasm` and its wheels, numpy among them, run by a Python host on wasmtime with no JavaScript) became its own project:
**[natify-sh/pyodide-wasmtime](https://github.com/natify-sh/pyodide-wasmtime)**. It went much further than the scripts that were here (the glue is wasm, both a fused and a dynamic build, sockets, `ctypes`/`cffi`, TLS, Pyodide's own CPython test suite in its CI).
The scripts of this folder were removed; they are in the history of wasmhost (before this commit). `numpy_check.py` moved to [`../dlopen/`](../dlopen/numpy_check.py), where it is used for numpy on CPython for WASI.
