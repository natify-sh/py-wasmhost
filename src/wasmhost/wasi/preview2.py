"""`wasmhost.wasi.preview2`: WASI 0.2 for a core module of ONE component (S0001, path 1).

The core module that `wasm-tools component unbundle` leaves has flat `wasi:*@0.2.N` imports, one memory exported as
`memory`, an export `cabi_realloc` and the export `wasi:cli/run@0.2.N#run`. Its imports are answered by the functions of
0.2 of `fusedwasi` over the same `fusedwasi.State` that `Preview1` uses, so `Preview2(state=p1.state)` sees the files,
arguments and streams of `p1`.

    code = Preview2(args=["prog"], env={"A": "1"}, stdout=sys.stdout.buffer.write).run(Module(wasm))

The network is denied unless the host says so: `network=True` opens it, `socket_addr_check(ip, port, use)` decides each
bind or connect (what `network` says is then the check's), `http=True` and `http_check` are the same for `wasi:http`
(`http_send(request) -> response` replaces the transport; `wasi:http` is unstable in fusedwasi).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from typing import Any

from fusedwasi import Exit, Guest, State, signatures

from .._api import Instance, Module
from .._errors import LinkError
from .preview1 import MASK32, MASK64, make_state


class Preview2:
    """The `wasi:*` calls of one program run (a core module of one component). The options of `Preview1`, and the
    policy: `network`, `socket_addr_check`, `allow_ip_name_lookup`, `http`, `http_check`, `http_send`, as fusedwasi's
    `State` names them (all deny). `state=` shares a `State` (its owner closes it; no other option is then given, as in
    `Preview1`).

    `import_map=` (a path, or the loaded JSON) is the file `meld fuse --emit-import-map` writes (schema 2), for a core
    module fused from SEVERAL components (S0004): each `wasi:*` import then reaches the memory and the `cabi_realloc`
    of its own component. It is used when the module exports more than one `cabi_realloc*`; a module with one is run as
    one component and the map is ignored (this includes a `meld --memory shared` fusion, where the one `cabi_realloc`
    serves every component: safe only with an allocator that does not free another component's blocks). A module with
    several and no map is refused.

    `run(module)` returns the result of the export `wasi:cli/run@0.2.N#run`: 0 is `ok`, 1 is `err` (the value `main`
    returned does not come out of it), or the code that `wasi:cli/exit` was given."""

    def __init__(
        self,
        args: Sequence[str] = (),
        env: Mapping[str, str] | None = None,
        preopens: Mapping[str, str | os.PathLike[str]] | None = None,
        stdin: bytes | bytearray | Any | None = None,
        stdout: Callable[[bytes], object] | Any | None = None,
        stderr: Callable[[bytes], object] | Any | None = None,
        *,
        readonly: bool | Collection[str] = False,
        network: bool = False,
        socket_addr_check: Callable[[str, int, int], bool] | None = None,
        allow_ip_name_lookup: bool | None = None,
        http: bool = False,
        http_check: Callable[[str, str], bool] | None = None,
        http_send: Callable[[Any], Any] | None = None,
        state: State | None = None,
        import_map: str | os.PathLike[str] | Mapping[str, Any] | None = None,
    ) -> None:
        policy = {
            "network": network,
            "socket_addr_check": socket_addr_check,
            "allow_ip_name_lookup": allow_ip_name_lookup,
            "http": http,
            "http_check": http_check,
            "http_send": http_send,
        }
        self._owns_state = state is None
        if state is not None:
            given = [
                args,
                env,
                preopens,
                stdin,
                stdout,
                stderr,
                readonly,
                network,
                socket_addr_check,
                http,
                http_check,
                http_send,
            ]
            if any(given) or allow_ip_name_lookup is not None or import_map is not None:
                raise TypeError("state= is the whole world of the program: no other option is given with it")
        else:
            state = make_state(args, env, preopens, stdin, stdout, stderr, readonly, **policy)
        self._state = state
        self._memories: list[Any] = []  # the memory and the cabi_realloc of the instance, set by bind (late binding)
        self._reallocs: list[Any] = []
        self._map = _load_map(import_map) if import_map is not None else None
        indexes = [e["memory"]["index"] for e in (self._map or {}).values() if _is_ref(e["memory"], "index")]
        self._ncomp = max(indexes, default=0) + 1  # memories the map routes to (1 without one)
        self._guest = Guest(state, [lambda i=i: self._memory(i) for i in range(self._ncomp)], realloc=self._realloc)

    @property
    def state(self) -> State:
        """The world of the program: give it to `Preview1(state=...)` or `Preview2(state=...)`."""
        return self._state

    def _memory(self, comp: int = 0) -> Any:
        if not self._memories:
            raise RuntimeError("the program has no memory yet: bind(instance) first")
        return self._memories[comp]

    def _realloc(self, comp: int, old: int, old_size: int, align: int, new_size: int) -> int:
        return self._reallocs[comp](old, old_size, align, new_size)

    def imports(self, module: Module) -> dict[str, dict[str, Callable[..., int | None]]]:
        """The import object for the `wasi:*` imports `module` declares (the names exactly as it declares them; a `$N`
        suffix is stripped to find the function). A `wasi:` import fusedwasi has no function for (WASI 0.3 too) is a
        `LinkError`. A module of several components (see `import_map=`): the `comp` of each import is read from the map,
        and an import that the map lacks, or that it could not trace, is a `LinkError`."""
        routed = self._routed(n for n in (e.name for e in Module.exports(module)))
        out: dict[str, dict[str, Callable[..., int | None]]] = {}
        for d in Module.imports(module):
            if d.kind != "function" or not d.module.startswith("wasi:"):
                continue
            row = signatures.find_import(d.module, d.name.split("$")[0])
            if row is None:
                raise LinkError(f"fusedwasi has no function for {d.module} {d.name}")
            comp = 0
            if routed:
                if d.name in out.get(d.module, {}):
                    raise LinkError(f"the module imports {d.module} {d.name} twice: it can not be routed")
                entry = (self._map or {}).get((d.module, d.name))
                if entry is None:
                    raise LinkError(f"the import map has no entry for {d.module} {d.name}")
                for what in ("memory", "realloc"):
                    if _is_ref(entry[what], "unknown"):
                        raise LinkError(
                            f"{d.module} {d.name}: the import map could not trace its {what}: {entry[what]['unknown']}"
                        )
                comp = entry["memory"]["index"] if _is_ref(entry["memory"], "index") else 0
            out.setdefault(d.module, {})[d.name] = self._call(row, comp)
        return out

    def _routed(self, names: Iterable[str]) -> bool:
        """Is the module of several components (several `cabi_realloc*` exports)? Refuse it when no map is given."""
        if sum(n.startswith("cabi_realloc") for n in names) < 2:
            return False
        if self._map is None:
            raise ValueError(
                "the module exports several cabi_realloc (it was fused from several components): give import_map=, "
                "made by `meld fuse --emit-import-map`, or fuse one component"
            )
        return True

    def _call(self, row: Any, comp: int = 0) -> Callable[..., int | None]:
        function = row.python_function()
        masks = tuple(MASK64 if p.type == "i64" else MASK32 for p in row.params)
        takes_comp, has_result = row.takes_comp, bool(row.results)

        def call(*args: int) -> int | None:
            masked = [a & m for a, m in zip(args, masks, strict=False)]
            result = function(self._guest, comp, *masked) if takes_comp else function(self._guest, *masked)
            return result if has_result else None  # type: ignore[no-any-return]

        return call

    def bind(
        self, instance: Instance, memories: Sequence[str] = ("memory",), reallocs: Sequence[str] = ("cabi_realloc",)
    ) -> None:
        """Give the host the memory and the `cabi_realloc` of the instance, by the names of their exports (for a module
        of several components the names are the map's, and `memories` and `reallocs` are not used)."""
        if self._routed(instance.exports):
            mem_names, realloc_names = ["memory"] * self._ncomp, ["cabi_realloc"] * self._ncomp
            for e in (self._map or {}).values():
                if _is_ref(e["memory"], "index"):
                    mem_names[e["memory"]["index"]] = e["memory"]["export"]
                    if _is_ref(e["realloc"], "export"):
                        realloc_names[e["memory"]["index"]] = e["realloc"]["export"]
            self._memories = [instance.exports[name] for name in mem_names]
            self._reallocs = [instance.exports[name] for name in realloc_names]
            return
        if len(memories) != 1 or len(reallocs) != 1:
            raise ValueError("one component: one memory and one cabi_realloc")
        self._memories = [instance.exports[name] for name in memories]
        self._reallocs = [instance.exports[name] for name in reallocs]

    def instantiate(self, module: Module, **options: Any) -> Instance:
        """`Instance(module, wasi.imports(module), **options)`, bound to this host."""
        instance = Instance(module, self.imports(module), **options)
        self.bind(instance)
        return instance

    def start(self, instance: Instance) -> int:
        """Call the export `wasi:cli/run@0.2.*#run`: its result (0 ok, 1 err), or the code given to `wasi:cli/exit`."""
        self.bind(instance)
        names = [n for n in instance.exports if n.startswith("wasi:cli/run@0.2.") and n.endswith("#run")]
        if not names:
            raise TypeError("the module exports no wasi:cli/run@0.2.N#run")
        try:
            entry: Any = instance.exports[names[0]]
            return int(entry())
        except Exit as exit_:
            return exit_.code

    def run(self, module: Module, **options: Any) -> int:
        """Instantiate, start, and close the world (a State given with `state=` stays open): the code of the program."""
        try:
            return self.start(self.instantiate(module, **options))
        finally:
            self.close()

    def close(self) -> None:
        """Close the files and streams of the world, unless it was given with `state=`. The memory and the
        `cabi_realloc` of the instance are let go of in either case: the functions linked into wasm3 hold this host
        in C, where the garbage collector does not look, so without it the runtime would never be freed (and wasm3
        has 128 at most in a process)."""
        self._memories = []
        self._reallocs = []
        if self._owns_state:
            self._state.close_all()

    def __enter__(self) -> Preview2:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _is_ref(value: Any, key: str) -> bool:
    return isinstance(value, dict) and key in value


def _load_map(source: str | os.PathLike[str] | Mapping[str, Any]) -> dict[tuple[str, str], Any]:
    """The `wasi:*` entries of a `meld fuse --emit-import-map` file (schema 2) by `(module, name)`."""
    data: Any = source
    if isinstance(source, (str, os.PathLike)):
        with open(source, encoding="utf-8") as f:
            data = json.load(f)
    if data.get("version") != 2:
        raise ValueError(
            f"the import map has version {data.get('version')!r}: only version 2 (meld 0.65 to 0.67) is read"
        )
    entries: list[Any] = data["imports"]
    return {(e["module"], e["name"]): e for e in entries if e["module"].startswith("wasi:")}
