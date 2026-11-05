# Specs

A spec is the contract of one change, written **before** the code and approved by the owner. The work of wasmhost is spec-driven: no backend feature, no new `supports(...)` string, no change of the public API, of the
self-test or of the WASI host is implemented without an approved spec that names it.

## When a spec is needed

* a new capability or a new form of the API (a method, a type, an option, a `supports` string);
* a change of what a backend does or reports (a feature added to or removed from a backend, a limit);
* the WASI host: a new version or interface of WASI, a change of an errno or of a record layout;
* anything that changes what SUPPORTS.md says.

Not needed: a bug fix that restores what the README already says, a test, a doc fix, a dependency bump. If in doubt, write the spec; it is short.

## Life of a spec

`draft` (written, not yet read by the owner) -> `approved` (the owner said so; the date is in the file) -> `implemented` (CI is green on the head that carries it; the file says which commit) -> `superseded` (a later spec
replaces it; the file names that one). An approved spec is changed in the spec first, then in the code. The agent that implements it works from the spec and the brief; the reviewer reads the diff against the spec.

## Files

`Snnnn-short-name.md`, numbered in order of writing, from `TEMPLATE.md`. This page is the index.

| Spec | What | Status |
|---|---|---|
| [S0001](S0001-wasi-0.2-on-one-state.md) | WASI 0.2: the class `Preview2`, one component first (B-606) | approved 2026-11-05; steps A (`Preview2`) and B (the command line) built |
| [S0002](S0002-gc-types.md) | GC types: the parser, the probes and the tests per backend (B-604) | draft |
| [S0003](S0003-several-memories.md) | several memories of one instance, the prerequisite of S0001 (B-603) | implemented 2026-11-05 (CI green on `be18649`) |
| [S0004](S0004-wasi-0.2-several-components.md) | WASI 0.2 of several components through meld's import map (B-606, path 2 of S0001) | draft |
