"""SUPPORTS.md from what CI measured.

CI runs `tests/test_feature_probes.py` on every backend (the jobs of tests.yml run the suite once per backend, on every
OS), and each run prints one line `WASMHOST-SUPPORTS {json}`: the engine, the OS, the Python, the features of the API
(`backend.supports`), whether a WASI 0.1 and a WASI 0.2 program ran, and which WebAssembly features the engine took
(`tests/feature_probes.py`). This script reads those lines from the logs of a CI run and writes the tables between the
`probe` markers of SUPPORTS.md.

    # LOG: a downloaded log of a job, or a folder of them
    uv run python tools/probe_features.py --collect LOG... --update SUPPORTS.md
    # tests/feature_probes.py: the bytes of every probe again, from the WAT next to them (needs wasmtime)
    uv run python tools/probe_features.py --regenerate
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINE = re.compile(r"WASMHOST-SUPPORTS (\{.*\})")
ORDER = ["wasmtime", "node", "bun", "wasm3", "jsc", "gi-jsc", "jscontext", "pyodide"]
CELL = {"yes": "yes", "no": "no", "parser": "not added to wasmhost"}
# `supports(...)` cells where the engine's Python binding can do something that wasmhost does not use: a "no" there is a
# "not added to wasmhost", not an engine limit. Measured by hand (2026-11-05, pywasm3 0.9.1.dev75), not by CI.
NOT_ADDED = {
    ("wasm3", "import.global"): "not added to wasmhost (pywasm3 links a value; the global is not shared)",
    ("wasm3", "threads"): "not added to wasmhost (a call from another thread ran in a trial)",
    ("node", "table.signatures"): "not added to wasmhost (`node --experimental-wasm-type-reflection` gives `.type()`)",
}


def regenerate() -> None:
    """The bytes in tests/feature_probes.py again, from the WAT kept beside each of them."""
    import wasmtime

    sys.path.insert(0, str(ROOT / "tests"))
    import feature_probes  # type: ignore[import-not-found]

    path = ROOT / "tests" / "feature_probes.py"
    text = path.read_text(encoding="utf-8")
    for name, (_edition, _expected, old, wat) in feature_probes.PROBES.items():
        new = bytes(wasmtime.wat2wasm(wat))
        if new != old:
            print(f"{name}: changed")
            text = text.replace(old.hex(), new.hex())
    path.write_text(text, encoding="utf-8")


def read(paths: list[str]) -> list[dict]:
    files: list[Path] = []
    for p in map(Path, paths):
        files += sorted(f for f in p.rglob("*") if f.is_file()) if p.is_dir() else [p]
    records: list[dict] = []
    seen: set[str] = set()
    for f in files:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            found = LINE.search(line)
            if found is None:
                continue
            record = json.loads(found.group(1))
            # `gh run view --log` lines are "job<TAB>step<TAB>time text": the JavaScriptCore steps that run
            # without the JIT (as on iOS) say so in their names
            parts = line.split("\t")
            if len(parts) >= 3 and "JIT off" in parts[1]:
                record["jit"] = "off"
            key = json.dumps(record, sort_keys=True)
            if key not in seen:  # the same line twice (the suite and the last step both print it) counts once
                seen.add(key)
                records.append(record)
    return records


def cell(values: dict[str, set[str]]) -> str:
    """One answer if every run agreed, else the answers with the platforms that gave them."""
    answers = {v for vs in values.values() for v in vs}
    if len(answers) == 1:
        return CELL[next(iter(answers))]
    by_answer: dict[str, list[str]] = defaultdict(list)
    for platform, vs in sorted(values.items()):
        for v in sorted(vs):
            by_answer[v].append(platform)
    return "; ".join(f"{CELL[a]} ({', '.join(p)})" for a, p in sorted(by_answer.items()))


def markdown(records: list[dict]) -> str:
    from importlib import util

    spec = util.spec_from_file_location("feature_probes", ROOT / "tests" / "feature_probes.py")
    assert spec is not None and spec.loader is not None
    fp = util.module_from_spec(spec)
    spec.loader.exec_module(fp)

    backends = [b for b in ORDER if any(r["backend"] == b for r in records)]
    runs: dict[str, list[dict]] = {b: [r for r in records if r["backend"] == b] for b in backends}
    out: list[str] = []

    def engines(b: str) -> str:
        names = sorted({r["engine"] for r in runs[b] if r["engine"] != "?"})
        return f"`{b}`" + (f" ({', '.join(names)})" if names else "")

    out += [
        "| WebAssembly feature | Edition | " + " | ".join(engines(b) for b in backends) + " |",
        "|---|---|" + "---|" * len(backends),
    ]
    for feature, (edition, _e, _d, _w) in fp.PROBES.items():
        cells = [cell(_by_platform(runs[b], lambda r, f=feature: r["features"][f])) for b in backends]
        out.append(f"| {feature} | {edition} | " + " | ".join(cells) + " |")

    api = sorted({a for r in records for a in r["api"]} | {"imports"})
    out += [
        "",
        "| `supports(...)` | " + " | ".join(f"`{b}`" for b in backends) + " |",
        "|---|" + "---|" * len(backends),
    ]
    for a in api:
        out.append(
            f"| `{a}` | "
            + " | ".join(
                NOT_ADDED.get((b, a), "no")
                if (c := cell(_by_platform(runs[b], lambda r, a=a: "yes" if a in r["api"] else "no"))) == "no"
                else c
                for b in backends
            )
            + " |"
        )

    out += [
        "",
        "| WASI program, run by a host of wasmhost | " + " | ".join(f"`{b}`" for b in backends) + " |",
        "|---|" + "---|" * len(backends),
    ]
    out.append(
        "| `wasi_snapshot_preview1` (`Preview1`): arguments, a file in a preopen, `fd_write`, `proc_exit` | "
        + " | ".join(cell(_by_platform(runs[b], lambda r: r["wasi"])) for b in backends)
        + " |"
    )
    if any("wasi2" in r for r in records):  # the logs of a run from before `Preview2` have no such field
        out.append(
            "| `wasi:*@0.2` of one component (`Preview2`): hello, environment, random, exit | "
            + " | ".join(cell(_by_platform(runs[b], lambda r: r.get("wasi2", "no"))) for b in backends)
            + " |"
        )

    out += ["", f"Measured by CI: {len(records)} different lines of the log, from these combinations:"]
    for b in backends:
        oses = sorted({r["os"] + (" (JIT off)" if r.get("jit") == "off" else "") for r in runs[b]})
        pys = sorted({r["python"] for r in runs[b]})
        out.append(f"- `{b}`: {', '.join(oses)}; {', '.join(pys)}")
    return "\n".join(out) + "\n"


def _by_platform(rs: list[dict], get) -> dict[str, set[str]]:  # type: ignore[no-untyped-def]
    values: dict[str, set[str]] = defaultdict(set)
    for r in rs:
        values[r["os"] + (", JIT off" if r.get("jit") == "off" else "")].add(get(r))
    return values


def main() -> None:
    args = sys.argv[1:]
    if "--regenerate" in args:
        regenerate()
        return
    if "--collect" not in args:
        raise SystemExit(__doc__)
    start = args.index("--collect") + 1
    stop = next((i for i, a in enumerate(args) if a.startswith("--") and i >= start), len(args))
    records = read(args[start:stop])
    if not records:
        raise SystemExit("no WASMHOST-SUPPORTS line in those logs")
    table = markdown(records)
    if "--update" in args:
        path = Path(args[args.index("--update") + 1])
        text = path.read_text(encoding="utf-8")
        begin, end = "<!-- probe:begin -->", "<!-- probe:end -->"
        head, rest = text.split(begin, 1)
        path.write_text(head + begin + "\n" + table + end + rest.split(end, 1)[1], encoding="utf-8")
    else:
        print(table)


if __name__ == "__main__":
    main()
