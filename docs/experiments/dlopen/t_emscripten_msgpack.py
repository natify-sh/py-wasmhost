import ssl, sys, importlib.machinery as m
print("ssl:", ssl.OPENSSL_VERSION)
sfx = ".cpython-315-wasm32-emscripten.so"
sys.path_hooks.insert(0, m.FileFinder.path_hook((m.ExtensionFileLoader, m.EXTENSION_SUFFIXES + [sfx]), (m.SourceFileLoader, m.SOURCE_SUFFIXES), (m.SourcelessFileLoader, m.BYTECODE_SUFFIXES)))
sys.path_importer_cache.clear()
import msgpack
print(msgpack.Packer.__module__)
d = {"a": [1, 2.5, "x", None, True], "b": b"bytes"}
print(msgpack.unpackb(msgpack.packb(d)) == d)
