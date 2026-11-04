# CLAUDE.md

Context and rules for working on wasmhost with an agent.

**Start with [`BRIEF.md`](BRIEF.md)**: what the project is, what it is not, and what is next.

## What this is
WebAssembly for Python with the shape of the JavaScript `WebAssembly` API, run by whatever engine the platform has (wasmtime, wasm3, Node, Bun, JavaScriptCore, a Pyodide host), plus a WASI 0.1 host over fusedwasi.
The main target is Pythonista on an iPhone (Python 3.10, standard library only). The direction was set by the owner on 2026-11-04: wasmhost goes its own way (no shared store or backend protocol with py-wasmext or
waboros), WASI is fusedwasi 0.1 and 0.2 over one state, and the work is to widen the support of features, backend by backend ([`ROADMAP.md`](ROADMAP.md)).

The maintainer communicates in Ukrainian; code, comments, commit messages and docs are in English.

## Hard rules
* **The package depends only on `fusedwasi`**, and runs on Python 3.10 with the standard library (Pythonista). Engines are optional extras or dev dependencies; a backend whose engine is missing says so, and is skipped.
* **The API stays close to the JavaScript WebAssembly API** (JavaScriptCore is the reference). The library is an alpha, so breaking old code for a cleaner API is allowed; when a new form is added, the old plain
  `int`/`float` form keeps working. No wrapper value types, no second API.
* **What an engine can not do is a `NotImplementedError` and `backend.supports(...) == False`**, never a silent no-op and never a fake.
* **One backend takes one call at a time** (a reentrant lock per backend). No threads by default; workers only on request (`threaded=True`), because the library must work where Python threads do not.
* **The work is spec-driven.** A new capability, a change of the API, of what a backend reports, of the WASI host or of what SUPPORTS.md says needs a spec in `docs/specs/` approved by the owner **before** the code; a contract is changed in its spec first. See `docs/specs/README.md`.
* **A feature comes with tests, a self-test step, a probe, and the README/BACKLOG.** The self-test (`wasmhost self test`, `wasmhost.selftest()`) runs on a device where CI does not exist; it is updated in the same change
  as the feature (`BACKLOG.md`, "Rule: the self-test ships together with the feature"). A new WebAssembly feature or backend gets a probe in `tests/feature_probes.py` and SUPPORTS.md is written again from CI (B-607).
* **Measure, do not guess.** What runs where is shown by a CI run (`SUPPORTS.md` is made from the logs of CI, `tools/probe_features.py`); a speed claim has the command and the numbers (`wasmhost bench`).
* **Nothing is pushed to `main`.** Every change goes through a pull request that the owner opens; the assistant works on a branch, does not open a pull request, rename the branch or squash history.
* **Do not bring in the designs of py-wasmext or waboros** (a store, an owner registry, a LIR): they are separate projects (BRIEF.md).

## How work is organised: one orchestrator, one subagent per step

The main session is the **orchestrator**. It does not implement steps itself: it chooses the next step, writes the brief, hands it to a subagent, **verifies** the result and fixes what the subagent got wrong. Every step of
implementation, investigation or measurement is done by a subagent with a fresh context, so the main session keeps the whole picture and stays small.

### Which model does what

| role | model | agent (`.claude/agents/`) | typical steps |
|---|---|---|---|
| **orchestrator** (main session) | **the strongest available** | — | pick the next step from `BACKLOG.md`, write briefs, verify, fix small mistakes, keep the docs true, ask the maintainer |
| implementer | **Sonnet** | `implementer` | one scoped step: a backend feature, the WASI host, the parser, tests, a self-test step, a probe |
| reviewer | **Opus** | `reviewer` | an independent read of a high-stakes diff against its spec (a backend, locks and threads, limits, the WASI host, the parser) with a fresh context and without the implementer's conclusions |
| runner | **Haiku** | `runner` | read CI logs and report which jobs failed and why, collect `SUPPORTS.md` from a CI run, run `wasmhost bench`, mechanical edits |

### A step, from start to end

1. **Choose** (orchestrator): the next open item of `BACKLOG.md`/`ROADMAP.md`. One step = one goal that a command (or a CI job) can confirm. If it cannot be stated that way, it is not a step yet. If the item changes a contract it needs a spec first (`docs/specs/`): write it from `TEMPLATE.md`, give it to the owner, wait for `approved`; only then brief an implementer.
2. **Brief** (orchestrator), using the template below. A subagent knows only what the brief says.
3. **Do** (subagent): works only inside the brief's scope; if the step needs more than the scope or the budget, **stops and reports**.
4. **Report** (subagent): files changed, the commands run and their output, what is left, questions. No claim without the command that shows it.
5. **Verify** (orchestrator): read the diff against the spec (inside the scope? under the budget? no new dependency, nothing for later, no unrelated edits?); run `uv run ruff check . && uv run ruff format --check .` and `uv run pyright`;
   check the docs (README, BACKLOG item, self-test step, SUPPORTS.md probe). **The tests are run by CI**: push the branch and read the jobs of Tests and Pre-commit on every platform; do not run the whole suite locally
   unless a failure needs reproducing. For the backends and the WASI host a `reviewer` reads the diff with no access to the implementer's reasoning.
6. **Fix** (orchestrator): a small mistake (about 20 lines, obvious) in the main session; anything larger goes back to a subagent with a precise list; a second failure on the same point goes to the maintainer.
7. **Close**: one commit per step (what and why), `git fetch` and `git pull --ff-only` first, push, and **look at CI**. A red CI is fixed at once, not left. `[x]` in BACKLOG means everything is done: implemented, tested
   (CI green, and said plainly where it was not run), the README and the self-test up to date, agreed with the owner.

### The brief (template)

```
Goal:        <one sentence, as a result a command or a CI job shows>
Context:     <what exists, which files; what was tried and ruled out>
Spec:        <the approved spec this step implements (docs/specs/Snnnn), or "none" with the reason (a bug fix, a test, a doc)>
Read first:  <the 1-3 documents or files that matter; not the whole repository>
Scope:       <files that may change>      Out of scope: <what must not change>
Budget:      <~N lines of diff; stop and report if more is needed>
Acceptance:  <exact commands and the CI jobs that must be green>
Docs:        <README, BACKLOG item, self-test step, SUPPORTS.md probe: which this step makes untrue>
Report:      files changed, commands run with output, docs updated, open questions
```

### Against over-engineering (applies to every agent)

* The smallest change that makes the acceptance command pass. No code "for later".
* No new module, class, layer, plugin point or option unless the brief names the need; no abstraction before its second real use.
* No rewrite of working code that the step does not require; no drive-by reformatting.
* When unsure between two designs, implement neither: report both with their costs.

## Working on the code
* A backend is one engine behind `Backend` (`src/wasmhost/_backend.py`): `_native.py` (wasmtime, wasm3), `_js.py` (Node, Bun), `_jsc.py`/`_capi.py` (JavaScriptCore), `_pyodide.py`. Every public method of a backend holds its
  lock; a host function called from inside a call may call into the same backend again (the lock is reentrant), but must not wait for another thread that wants the backend.
* `Backend.features` lists the `supports(...)` strings; a new capability is a new string, with `NotImplementedError` where it is missing, and a step in `_selftest.py` that asks `supports` first.
* The test modules for the self-test are built in `tests/wasm_builder.py`; `tests/test_selftest.py` checks that the bytes in `_selftest.py` match the builder.
* The WASI host follows the specification's witx files in `tests/data/wasi`; a difference from fusedwasi is fixed in fusedwasi, not here.
* Platform specifics (Windows, macOS, PyPy, free-threaded) are checked in CI; the owner checks the device (give a wheel, `uv build --wheel`, and a script, not a request to "try it").

## Commands
```
uv sync                                          # dev environment
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pytest -q --wasm-backend wasmtime         # one backend; also node, bun, wasm3, jsc, gi-jsc, jscontext (a backend that can not start fails the run)
node tests/pyodide_run.mjs pytest                # inside Pyodide (from the folder with node_modules/pyodide; see .github/workflows/tests.yml)
python -m wasmhost self test                     # the self-test, as on a device
python -m wasmhost bench                         # times the backends
python -m wasmhost run module.wasm [-- ARGS]     # a WASI command, or a function with --invoke
PATH=/usr/local/bin:$PATH uv tool run pre-commit run --all-files   # one run at a time: two in parallel corrupt each other; look at the result before committing
uv run python tools/probe_features.py --collect LOGS --update SUPPORTS.md   # the tables of SUPPORTS.md from the logs of a CI run
uv run python tools/probe_features.py --regenerate                          # the bytes of tests/feature_probes.py from their WAT
```
CI: `tests.yml` runs the suite once per backend on every OS and Python (and Pyodide, and WebKitGTK with and without JIT); `coverage.yml`, `pre-commit.yml`, `pypy-linux.yml`, `wasmgit.yml`, `publish.yml`.
