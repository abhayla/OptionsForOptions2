# Verifier brief: builder sequence row 10 (REQ-118 / W-138), Tier A, ROUND 2 (the last - a CRITICAL/MAJOR parks the row)

Independent, adversarial verifier; you did not build this and you did not run round 1. READ-ONLY: never edit, create,
commit or delete a tracked file in any checkout; scratch and mutation copies only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\verify-10r2`.

Code under test: worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, head
962ab74c (row 10 = 83707b70..962ab74c: build a11b61ee, finishes ae5fe864 and f9a8d780, fix 962ab74c; 83842bf3 is a
separate process item; the orchestrator's uncommitted docs/tests edits in the tree are not row 10's code). Round 1 brief
and its findings: `docs/process/builder-sequence-briefs/verify-row-10.md`, notes in `...\scratchpad\verify-10\`; the fix
brief `row-10-fix-1.md`. Spec: `spec/requirements/REQ-118.md` (every AC), F-60, ADR-017, ADR-094.

Round 1 found: CI red (margin-gate test signature, 6 login tests leaking a 429 cooldown across tests, a registry entry,
10 token-store fakes after row 9's 5-column read); u8b untested; a stray `-` bucket for keyless calls; AC-6's sender
not wired. Decided by the orchestrator: AC-6's real Notifier sender is deferred to #521 (an egress door, its own
reviewed item) - judge AC-6 on counting + one alert + the adapter only, and say whether that holds; MINORs in #522.
The fix put u8b's killing test at UNIT level (`tests/broker/test_rate_limit.py`), not through the door - judge whether
that kills the real risk.

Attack first: (1) re-check every round-1 finding is fixed IN CODE (not by a skip or a loosened guard); (2) the autouse
fresh-limiter fixture: does production still keep ONE limiter per process (grep its install path); could the fixture
hide a real cross-request leak? (3) keyless calls (the instrument download) now share the app's "other" bucket - prove
two calls (one keyless, one keyed) in one second are spaced; (4) re-run round 1's attacks 1-9 briefly; (5) write at
least 5 NEW mutants on the fix commit's code and run them through `python scripts/orchestrator/mutation_gate.py`,
results to your scratch folder; (6) the guard line and `-m repo_scan` and `tests/orchestrator` green.

Database: ONE run at a time (ADR-171): only through
`python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini -o faulthandler_timeout=60 <files>`
(it holds the lock; WAITING is correct). The fix's R13 run gave 1205 passed, 0 failed (`...\scratchpad\row10-fix1\final-db.log`)
- re-run only the files your attacks need. Known flaky, not this build:
`tests/test_edit_lint_hook.py::test_real_eslint_run_flags_unused_variable`.

Why Opus: Tier A (every Kite call, the margin gate's input, and a burst that could get the platform's key blocked).
BINDING: never stop a process by name; stop only PIDs you started. Kit guard: a shell command naming spec/, tools/,
.claude, factory, views or .github is blocked; use Read/Grep/Glob.

Return a JSON array, one object per AC: `{"row": 10, "req": "REQ-118", "ac": "AC-n", "result": "pass" | "fail" |
"partial" | "deferred", "commands": "...", "observed": "... file:line", "attack": "..."}`, then under 250 words: each
fail/partial with severity and the smallest fix, and anything not checked.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 40 min wall-clock, 70 tool calls
Report: evidence-table
