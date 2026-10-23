# Process item (meta review after row 9): mutation_gate.py and a night-hours hook on the question tool

Common brief: docs/process/builder-brief.md (Budget hard stop: at 64 calls start nothing new, commit, report).
Size: M, 7 files, 2 items
CI: kit tests job (`tests/orchestrator/test_mutation_gate.py`, `tests/hooks/test_question_night_guard.py`; vars: none).
Expected (orchestrator, before dispatch ~09:06 IST): build 45 min / ~170k; Tier A check (hook) 20 min / ~150k.

Core: a builder cannot report a row while a listed guard mutant survives, because a script - not the builder's memory -
runs every mutant and fails.
Proof: step 1 is `tests/orchestrator/test_mutation_gate.py` failing first: a tiny sample module with two guards and a
mutants file listing both, one killed by its named test and one not -> the gate exits 1 naming the survivor, and the
results file holds one line per mutant written as each finishes; with both killed it exits 0.

Spec basis: none - the spec says nothing about the delivery tooling (searched: mutation, gate, hook, question); this is
process tooling decided by the orchestrator from the meta review after row 9 (row-review.md), best practice.
Copy from: none - new process tooling; reuse the row-9 mutation scripts' shape (scratch `verify-09final\mutate.py`).

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, head 335485c7. The ROW 10
builder works in the same tree at the same time (backend/ofo/broker, backend/ofo_app/kite_*, order_limits_registry,
tests_app, tests/broker): touch none of those; commit ONLY your own paths with `git commit -F <msg> -- <your paths>` as
its own call; never `git add -A`, `stash`, `checkout --`, `reset`, `restore`; do NOT push. Kit files are read-only: the
settings file is GENERATED - edit `.claude/project/hooks.json` with the Edit tool, then run `python tools/kit_settings.py .`
as a bare command from the repo root (no pipe), and `python tools/kit_settings.py . --check`. Scratch:
`...\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\proc-gate`.

## What to build
1. `scripts/orchestrator/mutation_gate.py <checkout> <mutants.json> <results.jsonl>`: the mutants file is an
   allow-list of objects `{id, file, find, replace, test}` (`find` must occur exactly once in `file`, else the gate
   fails that mutant as unresolved - fail closed). For each: copy the checkout's needed tree to a scratch copy (never
   edit the checkout in place, R4), apply the edit, run `python -m pytest -q -p no:cacheprovider <test>` there with a
   per-mutant timeout (default 180 s; a timeout counts as NOT killed and is named), append `{id, result: killed |
   survived | timeout | unresolved, secs, summary}` to the results file at once (R18), and finally run the tests once
   on the unmutated copy (must pass). Exit 0 only when every mutant is killed and the clean run passes. `-c
   pytest-app.ini` passthrough for tests_app tests; a `--launcher` option that prefixes the throwaway-database runner.
2. Night-hours hook (R17 by machine): `scripts/hooks/question_night_guard.py`, wired in `.claude/project/hooks.json` as a
   PreToolUse hook on the question tool (AskUserQuestion): between 22:00 and 08:00 IST (the clock via the IST helper in
   `backend/ofo/timeutil.py` or `zoneinfo`, never a typed offset) it refuses with "owner may be away (22:00-08:00 IST):
   write the question to docs/process/owner-questions-<date>.md and keep building (row-review R17)"; an override env
   `OFO_QUESTION_NIGHT_OK=1` with a stated reason in the question text passes; any crash or missing file exits 0 (fail
   open, run-discipline E1).
Then add one line to `docs/process/builder-brief.md` quality bar: "Run `python scripts/orchestrator/mutation_gate.py`
on your attack-list mutants before reporting; quote its results file; a non-zero exit means not done."

Attack list: (each names its test file)
1. A surviving mutant -> exit 1 naming it; all killed -> exit 0 (`tests/orchestrator/test_mutation_gate.py`).
2. A `find` text occurring 0 or 2 times -> unresolved, exit 1 (same file).
3. A hanging test -> timeout, named, exit 1, within the timeout + 10 s (same file).
4. The checkout is byte-identical after a run (hash every file before/after) (same file).
5. The results file has one line per mutant even when the run is killed midway (lines appended as each finishes) (same file).
6. 23:30 IST -> the question tool is refused with the R17 text; 10:00 IST -> allowed; override passes; a crash exits 0
   (`tests/hooks/test_question_night_guard.py`).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes (the kit tests job already runs tests/); (c) the gate is an allow-list of mutant objects and fails closed on a `find` it cannot resolve exactly once; (d) pytest's answer states for a mutant run - passed, failed, error at collection, timeout, no tests collected - each mapped in the gate (only "failed" or "error" counts as killed; "no tests collected" is unresolved).
Threat model: in scope - a survivor reported as killed, an in-place edit of the checkout, lost results, a night question slipping through, a hook that blocks every session when it crashes; out of scope - a builder deliberately writing a wrong mutants file (the verifier writes its own).
Findings checked: guard-as-forbidden-list, wall-clock-assertion-flakes-under-load, dependent-tests-not-run-stale-later
Reviewer checklist: fail closed on unresolved; scratch copies only; results appended per mutant; timeout named; hook
fail-open and IST from the clock helper; settings regenerated by the kit tool and `--check` green; no new duplicated
literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the
PR beyond the settings file the kit tool writes.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table
