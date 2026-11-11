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
import subprocess
import sys
import threading
import time

_P = ctypes.c_void_p


def worker(scenario: str, seconds: float, gc_thread: bool) -> int:
    from wasmhost._capi import CApi, load_library

    lib = load_library()
    lib.JSGlobalContextCreate.restype = _P
    lib.JSGlobalContextCreate.argtypes = [_P]
    lib.JSGarbageCollect.restype = None
    lib.JSGarbageCollect.argtypes = [_P]
    ctx = lib.JSGlobalContextCreate(None)
    api = CApi(lib, ctx)

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
    stop.set()
    print(f"OK iterations={done} mismatches={mismatches} collections={collections[0]}", flush=True)
    return 1 if mismatches else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=int, default=6)
    ap.add_argument("--seconds", type=float, default=20)
    ap.add_argument("--scenario", choices=["evaluate", "nested", "both"], default="both")
    ap.add_argument("--gc-thread", choices=["on", "off", "both"], default="both")
    ap.add_argument("--worker", choices=["on", "off"], help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.worker:
        return worker(args.scenario, args.seconds, args.worker == "on")

    exit_code = 0
    for mode in ("off", "on") if args.gc_thread == "both" else (args.gc_thread,):
        failed = 0
        for run in range(1, args.runs + 1):
            proc = subprocess.run(
                [sys.executable, "-X", "faulthandler", __file__, "--worker", mode, "--scenario", args.scenario]
                + ["--seconds", str(args.seconds)],
                capture_output=True,
                text=True,
            )
            last = (proc.stdout.strip().splitlines() or ["(no output)"])[-1]
            crashed = proc.returncode < 0 or "Fatal Python error" in proc.stderr
            bad = crashed or proc.returncode != 0
            failed += bad
            kind = "CRASH" if crashed else ("MISMATCH" if bad else "ok")
            print(f"gc-thread={mode} run {run}: {kind} (exit {proc.returncode}) {last}", flush=True)
            if crashed:
                tail = [ln for ln in proc.stderr.splitlines() if ln.strip()][:12]
                print("    " + "\n    ".join(tail), flush=True)
        print(
            f"== gc-thread={mode}: {failed} of {args.runs} runs failed ({args.scenario}, {args.seconds:g} s each)",
            flush=True,
        )
        exit_code |= failed > 0
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
