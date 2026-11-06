import sys, importlib.machinery as m

sfx = ".cpython-315-wasm32-emscripten.so"
sys.path_hooks.insert(
    0,
    m.FileFinder.path_hook(
        (m.ExtensionFileLoader, m.EXTENSION_SUFFIXES + [sfx]),
        (m.SourceFileLoader, m.SOURCE_SUFFIXES),
        (m.SourcelessFileLoader, m.BYTECODE_SUFFIXES),
    ),
)
sys.path_importer_cache.clear()
import bitarray
import bitarray

print("import ok", bitarray.__version__, flush=True)
a = bitarray.bitarray("1011")
print("create ok", flush=True)
print(a, flush=True)
a.extend([1, 0, 1])
print("extend ok", flush=True)
print(a.count(), flush=True)
print(a.tolist(), flush=True)
