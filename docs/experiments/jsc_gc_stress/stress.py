"""Stress test of the hypothesis in BACKLOG ("the `jsc` backend on macOS").

The hypothesis: JavaScriptCore's collector frees a value that Python holds between an API call and `JSValueProtect`,
because ctypes keeps the JSValueRef in a Python int, not on the machine stack.

    uv run python docs/experiments/jsc_gc_stress/stress.py [--runs 6] [--seconds 20] [--scenario evaluate|nested|both]

A worker process makes `CApi.evaluate` calls in a loop (`nested` also calls `evaluate` from a JavaScript-to-Python
callback, as a host function does) and compares every answer with the expected text. With `--gc-thread on` a second
thread calls `JSGarbageCollect` in a tight loop (ctypes drops the GIL in a CDLL call, so it runs at the same time),
which asks the engine for collections much more often than a program does by itself. The control (`--gc-thread off`)
should not crash. A run is failed when the worker dies of a signal (a segmentation fault) or an answer differs.

If the hypothesis is right, `on` fails far more often than `off`. If both give zero failures in many runs, this window
is not the cause (or the stress does not reach it: say which). Not part of the library, not in CI by default.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import re
import subprocess
import sys
import threading
import time

_P = ctypes.c_void_p


def evaluate_rooted(api, src: str) -> str:
    """`CApi.evaluate` with the result kept in a JavaScript array until it is text, so that no collection can free it.

    The script pushes its own value into `globalThis.__wh_roots` before it returns; the pop comes after `_text`.
    (An indirect `eval` gives the value of the last expression, as `JSEvaluateScript` does.) For the experiment only.
    """
    c = api._c
    ref = api.ref
    wrapped = (
        "(function(){var r=(0,eval)("
        + json.dumps(src)
        + ");(globalThis.__wh_roots||(globalThis.__wh_roots=[])).push(r);return r})()"
    )
    script = api._string(wrapped)
    exception = ctypes.c_void_p()
    try:
        value = c.JSEvaluateScript(ref, script, None, None, 1, ctypes.byref(exception))
    finally:
        c.JSStringRelease(script)
    try:
        if exception.value or not value:
            raise RuntimeError("evaluate_rooted failed")
        return api._text(ref, value)
    finally:
        pop = api._string("__wh_roots.pop()")
        try:
            c.JSEvaluateScript(ref, pop, None, None, 1, None)
        finally:
            c.JSStringRelease(pop)


def evaluate_protect_first(api, src: str) -> str:
    """`CApi.evaluate` as it was, with `JSValueProtect` called first after the engine returns (one call shorter window).

    The cheap candidate: it keeps the fast script path, unlike the indirect `eval` of `evaluate_rooted`."""
    c = api._c
    ref = api.ref
    script = api._string(src)
    exception = ctypes.c_void_p()
    value = c.JSEvaluateScript(ref, script, None, None, 1, ctypes.byref(exception))
    held = exception.value or value
    if held:
        c.JSValueProtect(ref, held)
    c.JSStringRelease(script)
    try:
        if exception.value:
            raise RuntimeError(f"[JS] {api._text(ref, exception.value)}")
        return api._text(ref, value)
    finally:
        if held:
            c.JSValueUnprotect(ref, held)


def worker(scenario: str, seconds: float, gc_thread: bool, variant: str) -> int:
    from wasmhost._capi import CApi, load_library

    lib = load_library()
    lib.JSGlobalContextCreate.restype = _P
    lib.JSGlobalContextCreate.argtypes = [_P]
    lib.JSGarbageCollect.restype = None
    lib.JSGarbageCollect.argtypes = [_P]
    ctx = lib.JSGlobalContextCreate(None)
    api = CApi(lib, ctx)
    if variant == "rooted":
        api.evaluate = lambda src: evaluate_rooted(api, src)  # type: ignore[method-assign]
    elif variant == "protectfirst":
        api.evaluate = lambda src: evaluate_protect_first(api, src)  # type: ignore[method-assign]

    stop = threading.Event()
    collections = [0]

    def collector() -> None:
        while not stop.is_set():
            lib.JSGarbageCollect(ctx)
            collections[0] += 1

    if gc_thread:
        threading.Thread(target=collector, daemon=True).start()

    def handler(args: list[str]) -> str:
        return api.evaluate("'n' + " + args[0] + " + '-' + 'y'.repeat(40)")

    api.set_function("host", handler, "ERR")

    mismatches = 0
    done = 0
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        i = done
        if scenario in ("evaluate", "both"):
            want = f"{i}-" + "x" * 100 + '{"a":[1,2,3]}'
            got = api.evaluate(f"{i} + '-' + 'x'.repeat(100) + JSON.stringify({{a: [1, 2, 3]}})")
            mismatches += got != want
        if scenario in ("nested", "both"):
            want = f"n{i}-" + "y" * 40
            got = api.evaluate(f"host(String({i}))")
            mismatches += got != want
        done += 1
        if done % 50000 == 0:
            print(f"progress {done}", flush=True)  # a crashed run still tells how far it got
    stop.set()
    print(f"OK variant={variant} iterations={done} mismatches={mismatches} collections={collections[0]}", flush=True)
    return 1 if mismatches else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=int, default=6)
    ap.add_argument("--seconds", type=float, default=20)
    ap.add_argument("--scenario", choices=["evaluate", "nested", "both"], default="both")
    ap.add_argument("--gc-thread", choices=["on", "off", "both"], default="both")
    ap.add_argument(
        "--variant",
        choices=["control", "rooted", "protectfirst"],
        default="control",
        help="rooted: results kept in a JS array",
    )
    ap.add_argument("--worker", choices=["on", "off"], help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.worker:
        return worker(args.scenario, args.seconds, args.worker == "on", args.variant)

    exit_code = 0
    for mode in ("off", "on") if args.gc_thread == "both" else (args.gc_thread,):
        failed = 0
        total = 0
        for run in range(1, args.runs + 1):
            proc = subprocess.run(
                [sys.executable, "-X", "faulthandler", __file__, "--worker", mode, "--scenario", args.scenario]
                + ["--seconds", str(args.seconds), "--variant", args.variant],
                capture_output=True,
                text=True,
            )
            lines = proc.stdout.strip().splitlines()
            last = lines[-1] if lines else "(no output)"
            found = re.search(r"iterations=(\d+)", last)
            if found:
                iterations = int(found.group(1))
            else:  # a crashed run: the last progress line
                progress = [int(ln.split()[1]) for ln in lines if ln.startswith("progress ")]
                iterations = progress[-1] if progress else 0
                last = f"after about {iterations} iterations"
            total += iterations
            crashed = proc.returncode < 0 or "Fatal Python error" in proc.stderr
            bad = crashed or proc.returncode != 0
            failed += bad
            kind = "CRASH" if crashed else ("MISMATCH" if bad else "ok")
            print(f"gc-thread={mode} run {run}: {kind} (exit {proc.returncode}) {last}", flush=True)
            if crashed:
                tail = [ln for ln in proc.stderr.splitlines() if ln.strip()][:12]
                print("    " + "\n    ".join(tail), flush=True)
        print(
            f"== gc-thread={mode}: {failed} of {args.runs} runs failed, total iterations {total} "
            f"({args.scenario}, {args.seconds:g} s each)",
            flush=True,
        )
        exit_code |= failed > 0
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
