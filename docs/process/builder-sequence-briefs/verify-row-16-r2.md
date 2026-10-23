# Verifier brief: row 16 round 2 (REQ-038 / W-144), findings-only (ADR-178 (1)) plus one new order file

Independent, adversarial verifier; you built none of it. READ-ONLY: never edit, create, commit or delete a tracked
file. Scratch and mutation copies only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\5db71e90-61e3-4f1b-8a6c-a0ee38c54e11\scratchpad\verify-16-r2`.

Code: worktree `D:\Abhay\Ventures\OptionsForOptions2-row-16`, branch `build/seq-row-16` (fix commits 9698f26d, 6d2a924d,
4069e9d0, 735ba1a6 on top of d99b2097). Fix brief: `docs/process/builder-sequence-briefs/row-16-fix-1.md` (in the
`-builder-reqs` worktree). Round 1 findings (re-check exactly these):
1. AC-4 MAJOR: the domain's reconciliation_required flag was lost between requests (`_replay`).
2. AC-3 MAJOR: activation matched plans by time only; any ENTRY plan after confirmation activated the proposal.
3. AC-2 MINOR: once a version row existed, the open-plan (IN_FLIGHT) refusal never fired.
4. AC-5 MINOR: a proposed version could not be read back (VersionOut had no definition).
5. MINOR: the 0022 trigger did not check INSERTs (an `active` row could be inserted directly).
6. Four surviving mutants: drift/undecidable check (execution_return ~:361), PARTIAL treated as superseded, the
   after-confirmation filter, `nothing_placed` treated as complete.

Also judge (the builder departed from the brief, citing the spec):
7. Manual same-direction units are NOT counted as the strategy's and do NOT set the flag (cites ADR-109 "is shown as
   outside lots and blocks no strategy"). Read ADR-109 and say whether the code matches it.
8. No return clears the flag; only a recorded manual resolution would, and no app path writes it yet (cites REQ-060
   Q222 "an agreeing reconciliation run does not unblock a strategy by itself"). Read REQ-060 and say whether the code
   matches, and whether a flagged strategy can ever be unblocked today (if not: severity, and is that acceptable while
   no live plan can activate a proposal?).
9. Execute is not refused by the new flag. ADR-018: an unresolved reconciliation mismatch blocks execution. Find
   whether the Execute route already blocks on a live mismatch through its own reconciliation (file:line); if it does,
   is the sticky flag a gap that matters (a mismatch the live check no longer sees)? Severity.
10. New order file: `backend/ofo_app/execution_plan_store.py` (round 1 did not read it) and the plan-version write in
   `backend/ofo_app/routes/execute.py`: read the changed lines fully; a plan must never be written with a wrong
   version number, and an unreadable version must fail closed.

Database: run NO database test locally; CI on PR #525 runs them after the orchestrator merges this branch. Mutation:
mutants needing a DB cannot run here; for each, say whether its named test asserts the mutated line (read the test).
DB-free tests you may run: python -m pytest -q -p no:cacheprovider tests/strategy tests/reconciliation tests/errors/test_template_pins.py tests/test_no_broker_name_in_feature_code.py; python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_response_door.py tests_app/test_openapi_drift.py

Why Opus: Tier A - order-path store and reconciliation (broker state wins, ADR-016..019), migration 0023.
BINDING: never stop a process by name. Kit guard: a shell command naming spec/, tools/, .claude, factory, views or
.github is blocked; use Read/Grep/Glob.

Return a JSON array, one object per finding 1-10: `{"n": 1, "result": "fixed" | "not fixed" | "partial" | "new
issue", "severity": "CRITICAL|MAJOR|MINOR|none", "observed": "file:line", "evidence": "command + result line"}`, then
under 250 words: verdict PASS / FAIL for row 16 round 2, and the smallest fix for each open item.
Budget: 20 min wall-clock, 30 tool calls (the verifier's turn limit is 40; batch commands)
Report: evidence-table
