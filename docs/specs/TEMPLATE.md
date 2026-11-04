# Snnnn: <name>

Status: draft | approved <date> | implemented <commit> | superseded by Snnnn
Backlog: <B-nnn>

## Goal
One paragraph: what a user can do after this that they can not do now, as a result a command or a CI job shows.

## Context
What exists (files, `supports` strings, backends), what was tried and ruled out, what the engines and fusedwasi already do. Facts with their source (a CI run, a command, a file); a guess is marked as a guess.

## The contract
The shape that is promised: the API (names, arguments, results, errors), the `supports(...)` strings, the behaviour on a backend that lacks it (`NotImplementedError`), what does not change.

## Matrix
| Backend | Done by | Expected | Notes |
|---|---|---|---|
One row for each of: wasmtime, wasm3, node, bun, jsc, gi-jsc, jscontext, pyodide.

## Tests and probes
* the tests (file, what each checks), the self-test step, the probe in `tests/feature_probes.py`;
* the CI jobs that must be green, and the SUPPORTS.md rows that change.

## Out of scope
What this spec does not do, so that nobody widens it.

## Open questions
For the owner. A spec is not approved while one blocks the work.

## Changes
Date, what changed, why (after approval).
