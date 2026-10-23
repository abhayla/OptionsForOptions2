# Process item (chunk 2, ADR-178 one per chunk): the reach check - verified evidence must test code the product calls

Common brief: docs/process/builder-brief.md (Budget hard stop: at 64 calls start nothing new, commit, report). Run
`python scripts/orchestrator/mutation_gate.py` on the new check before reporting; write the results to a file in your
scratch folder and quote it (R18).
Size: M, 4-6 files, 5 items
CI: kit tests job (`tests/orchestrator/test_reach_check.py` (new), `tests/test_reach_check_real.py` (new, marked
`repo_scan`); vars: none). No database.
Expected (orchestrator, before dispatch, clock 2026-10-24 morning): 60 min / ~300k.

Core: one command lists, per requirement whose status is Verified or whose owning work item is in_review/done, every
passing evidence file whose tested product modules no app entry point reaches - and exits 1 on a NEW one.
Proof: step 1 - run it on a REAL old tree where the finding was measured: extract commit 7a0512a3's PARENT
(`git archive 7a0512a3^ | tar -x -C <scratch>/old`; the tree before GC-3 P0 re-verdicted REQ-058/060) and show the
script flags REQ-060 (evidence on `ofo.reconciliation.compare` / `resolution`) and REQ-058 (`ofo.execution.partial`),
while it passes at least one requirement whose tests import a module the app does import (name it). Then run it on the
current tree and record every hit. Write both outputs to your scratch folder and quote the counts.

Spec basis: finding `verified-on-a-module-the-product-does-not-call` (knowledge/findings), detection note: "A check
could list, per Verified requirement, the modules its evidence's test files import and fail when no route/app module
imports them; not built." Session-5 handover NEXT 4: "per Verified/in_review requirement, the modules its evidence
tests import must be imported by a route/app module". ADR-178: "process-tool work is frozen until the chunk-1 PR, then
at most one item per chunk on Sonnet" - this is chunk 2's one item.
Copy from: none - orchestration tooling, no legacy module.
Reference: none - searched evidence check, reachability (tooling, no screen).
Findings checked: verified-on-a-module-the-product-does-not-call, guard-by-banned-shapes, repo-wide-scan-outside-targeted-tests
Threat model: in scope - an honest builder's evidence naming tests that exercise only a domain module no app entry
point (transitively) imports; renamed/aliased imports (`import ofo.x as y`, `from ofo import x`), relative imports
inside backend, re-exports through a package `__init__`, and dynamic imports (`importlib.import_module`, `__import__`)
which are UNRESOLVED and fail closed; evidence naming no test file, or a test file that is missing or does not parse
(fail closed, listed by name). Out of scope - forged evidence, tests that import a reached module but assert on an
unreached one through reflection, and runtime-only wiring the AST cannot see (record each such case as a baseline entry
with its reason, never silently pass).
Standing items: (a) n/a: no time-budgeted job, it is a one-shot scan; (b) the new test imports only the standard
library and runs in the existing kit tests job after its install step, no CI file changes; (c) applied - the detector
resolves imports by module path from the AST (import source, never identifier text), and any import shape it cannot
resolve (dynamic import, star import from an unknown module, unparseable file) is a failure naming the file, not a pass;
(d) n/a: it reads only repo files, no other system's answer.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-OptionsForOptions2-chunk2-process`, branch `build/seq-chunk2-process`
(from `build/seq-chunk-2` cf30134e) - its OWN worktree; no other agent works there. Commit with
`git commit -F <msg-file> -- <your paths>`; do NOT push. Never stop a process by name. Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\06fe7549-4596-4e85-8261-0804902d0768\scratchpad\reach-check`.
The kit guard blocks any shell command whose TEXT names `spec`, `.claude`, `views`, `factory`, `tools/` or `.github`:
read those with Read/Grep/Glob; build such paths inside Python code, not on the command line.

## What to do
1. `scripts/orchestrator/reach_check.py` (standard library only):
   - Entry points: the FastAPI app module(s) under `backend/ofo_app/` (find where the app object is built and every
     router it includes); the reached set = every `ofo.*` / `ofo_app.*` module transitively imported from them (AST
     over `backend/ofo` and `backend/ofo_app`; a `from pkg import name` where `name` is a submodule counts as importing
     the submodule; a package `__init__` that re-exports counts its imports).
   - Requirements in scope: status `Verified` in the requirement file's frontmatter, OR any owning work item
     (`work/W-*.md`, its requirement field) with status `in_review` or `done`.
   - For each in-scope requirement: its passing evidence files (`evidence/<W-id>/<AC-id>.md` whose result is pass)
     -> the test files each names (`tests/...py`, `tests_app/...py`, with or without `::name`) -> the `ofo.*` /
     `ofo_app.*` modules each test file imports. An AC is REACHED when at least one tested product module is in the
     reached set (a test importing `ofo_app` routes or the app client counts as reached). UNREACHED when none is.
     UNRESOLVED when the evidence names no test file, a named file is missing or does not parse, or a tested module
     uses a dynamic import shape.
   - Output one line per non-reached AC: `UNREACHED|UNRESOLVED REQ-### W-### AC-n <test file> <modules>`; summary
     counts; `--json` for machines.
   - Baseline: `scripts/orchestrator/reach_check_baseline.json` lists today's accepted hits, each with a one-line reason
     and an issue number or "owner decision" - only for hits you prove are wired another way (say how) or already
     tracked. Exit 1 on any hit not in the baseline AND on any baseline entry that no longer occurs (stale entries must
     be deleted, so the list only shrinks).
2. `tests/orchestrator/test_reach_check.py`: synthetic mini-trees in tmp_path - reached via a route, reached via a
   re-export, aliased import, unreached domain module, evidence naming no test file, missing test file, dynamic
   import -> UNRESOLVED, stale baseline entry -> exit 1.
3. `tests/test_reach_check_real.py` marked `repo_scan`: runs the check on this repo; it must exit 0 with the baseline.
4. Real hits on today's tree: for each, decide - genuinely unreached (put in the baseline with the issue to file: list
   them in your report, the orchestrator files ONE issue for all) or wired another way (baseline with the proof
   file:line). Never edit evidence, requirement or work-item status.
5. Finding update: in `knowledge/findings/verified-on-a-module-the-product-does-not-call.json` set detection
   `status` to `guarded`, add the check (`scripts/orchestrator/reach_check.py`, `tests/test_reach_check_real.py`) to
   `checks`, and replace the "not built" note. Do NOT regenerate the findings index (generated files stay out; the
   orchestrator regenerates).

Run each attack yourself before reporting; the reviewer repeats them.
Attack list:
1. Delete the import of a reached domain module from its only app caller in a scratch copy -> the AC it backs turns
   UNREACHED.
2. `import ofo.engine.pricing as p` and `from ofo.engine import pricing` both resolve to `ofo.engine.pricing`.
3. A test that imports only `ofo.x` where `ofo/x/__init__.py` re-exports from `ofo.x.y`, and the app imports `ofo.x`
   -> reached.
4. `importlib.import_module("ofo.y")` in an app module -> UNRESOLVED named, not silently reached.
5. Evidence whose text names `tests/foo.py::test_a` -> the file is found and parsed.
6. A baseline entry that no longer occurs -> exit 1 naming it.
7. Mutation gate over the decision function(s): every mutant killed or explained.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Also run `python scripts/ruff_ratchet.py` and the two new test files. No full suite.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table (under 300 words): the proof counts on the old tree and today's tree, every real hit with its
decision, mutation-gate result line, the commit sha, and anything not done with its next command.
