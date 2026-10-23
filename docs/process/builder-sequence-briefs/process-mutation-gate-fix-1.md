# Process item fix 1: mutation_gate.py - two guards with no killing test, pre-failing mutants recorded as killed

Common brief: docs/process/builder-brief.md (Budget hard stop: at 24 calls start nothing new, commit, report).
Size: S, 2 files, 4 items
CI: kit tests job (`tests/orchestrator/test_mutation_gate.py`; vars: none). No database.
Expected (orchestrator, before dispatch, clock 09:3x): 20 min / ~100k.

Core: a mutant counts as killed only when its named test passes on the clean code and fails on the mutant.
Proof: step 1 is a new test failing first: a mutants file whose named test already FAILS on clean code -> the gate
exits 1, that mutant's line says `unresolved` (not `killed`), and `__clean__` is named.

Spec basis: none - the spec says nothing about the delivery tooling (searched: mutation, gate); process tooling, best
practice; Tier A check of 83842bf3 (verify-procgate, 2026-10-23): FAIL on G7 and G9.
Copy from: none.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-process`, branch `build/seq-process` (head 83842bf3) - its OWN worktree
(ADR-171 rule 12): never write in another worktree. Commit with `git commit -F <msg> -- <your paths>`; do NOT push.
Scratch: `...\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\proc-gate-fix1`. The checker's probes and mutants:
`...\scratchpad\verify-procgate\` (mutants.json, mutants2.json, probe.py, probe.log).

## What to do
1. G9: run each mutant's named test on the CLEAN copy first; a test that does not pass clean makes that mutant
   `unresolved` (never `killed`), and the gate exits 1; a test for it (named test failing clean -> unresolved, exit 1).
2. G7: a test that proves the checkout is untouched WHILE a mutant runs (read the checkout's file during a hanging
   mutant, or kill the gate mid-run and compare hashes) - red when `copytree` is replaced by the checkout itself.
3. G6 and G2/G10 (MINOR): the outside-path test uses an absolute path to a real file outside the checkout; a test that
   produces pytest exit 5 (no tests collected) -> unresolved; a mutant with an extra key is refused.
4. P7/P8 (MINOR): a file that is not UTF-8 -> that mutant `unresolved` with a line written, the run continues; the help
   text says a `find` must match the file's line endings (CRLF on a Windows checkout).
Then run the checker's mutants (`verify-procgate\mutants.json`, `mutants2.json`) through the gate itself: every one
killed; quote the results file.

Attack list: (each names its test file)
1. A named test failing on clean code -> unresolved, exit 1 (`tests/orchestrator/test_mutation_gate.py`).
2. The checkout byte-identical DURING a mutant run (same file).
3. An absolute outside path is refused (same file).
4. Pytest exit 5 -> unresolved (same file).
5. A non-UTF-8 file -> unresolved, a line written, the next mutant still runs (same file).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes; (c) the gate stays an allow-list of mutant keys and fails closed on what it cannot resolve; (d) pytest's answer states - 0 passed, 1 failed, 2 interrupted, 3 internal error, 4 usage error, 5 no tests - each mapped in one table in the gate with a test per state.
Threat model: in scope - a mutant recorded killed when nothing proved it, an in-place edit of the checkout, a crash that loses results; out of scope - a deliberately wrong mutants file.
Findings checked: guard-as-forbidden-list, wall-clock-assertion-flakes-under-load
Reviewer checklist: clean-run per named test; killed only on 1 (failed) after a clean 0; every answer state tested;
scratch copies only; no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted
tests only; no regenerated files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 20 min wall-clock, 30 tool calls
Report: evidence-table
