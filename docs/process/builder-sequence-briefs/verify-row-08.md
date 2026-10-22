# Verifier brief: builder sequence row 8 (REQ-050 shared computation / W-136), Tier A, ROUND 2 (the last)

Independent, adversarial verifier; you did not build this and you did not run round 1. READ-ONLY: never edit, create,
commit or delete a tracked file in any checkout (no in-place mutation); scratch and mutation copies only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\verify-08r2`.

Code under test: worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, head
<HEAD> (row-8 build = 5844a0c3^..<HEAD>; fix round 1 = 0d6f2dad, 85de202e; fix round 2 = e79086cf..<HEAD>). Spec:
`spec/requirements/REQ-050.md` (every AC), ADR-053 (V1: each user's own feed, so the feed owner is in every key),
ADR-012. Builder briefs: `docs/process/builder-sequence-briefs/row-08-REQ-050-shared-compute.md`, `row-08-fix-1.md`,
`row-08-fix-2.md` - run every item of their `Attack list:` again, with the variables of the CI job on their `CI:` line.

Round 1 found (PARTIAL): planned-entry and tracking routes bypassed the shared cache; the 100-concurrent test did not
discriminate; per-contract Greeks were still computed per strategy (`table/model.py:252`); no test killed mutation
M15 (forward key without the spot); 3 app files unrun (tunnel drop). Check each is fixed IN CODE, then attack fresh.

Attack first: (1) through the REAL outcome path on the recorded frames
(`tests/fixtures/kite_ws/frames-2026-10-08-092000-10s.bin.gz`), two readers of one snapshot: the second computes 0 IV,
0 Greeks, 0 forwards - and its numbers equal an unshared read exactly; (2) every route that calls `read_snapshot` or
builds an outcome (grep them all, not only the three named) passes a FeedScope when there is a feed owner; (3) two
users' feeds with identical data never share any figure; (4) the cache key of each figure (leg_iv, leg_greeks,
forward) holds every input its computation reads - mutate each key part away in a scratch copy and name the test that
goes red; (5) the no-lock mutation makes the 100-concurrent test red; (6) at 15:30:01 IST an expiring contract is not
valued with time left; (7) AC-2: nothing per-strategy (P&L, scenario) is cached across strategies; (8) R13: run
`scripts/orchestrator/select_app_tests.py`-style selection for the row's backend diff and run every file it names
through the throwaway-database runner.

AC-4 (load tests at 5,000-6,000 users) is DEFERRED by the orchestrator (ADR-053 V1 is per-user feeds; a load test
belongs to the shared-feed design): report it as `deferred` unless the code claims otherwise.

Known failing, not this build: `tests/test_edit_lint_hook.py::test_real_eslint_run_flags_unused_variable` (local
ESLint environment) and `tests_app/test_broker_status_route.py::test_core_proof_a_stored_session_reads_connected_and_ending_it_reads_disconnected`
(fails identically on main, clock skew). DB tests through the throwaway-database runner:
`python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/<file>.py`
(creates and drops its own database only; if it fails to connect, the SSH tunnel dropped: say so, do not count it as a
test failure).

Why Opus: Tier A (live-data figures every user's P&L is built on; a wrong shared key serves one snapshot's numbers to
another).

Return a JSON array, one object per AC: `{"row": 8, "req": "REQ-050", "ac": "AC-n", "result": "pass" | "fail" |
"partial" | "deferred", "commands": "...", "observed": "... file:line", "attack": "..."}`, then under 250 words: each
fail/partial with severity (CRITICAL / MAJOR / MINOR) and the smallest fix, and anything not checked and why.
Budget: 40 min wall-clock, 70 tool calls
Report: evidence-table
