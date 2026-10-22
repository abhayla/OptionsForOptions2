# Verifier brief: builder sequence row 9 part A0 (REQ-113 / W-137), Tier A, ROUND 2 (the last for this row)

Independent, adversarial verifier; you did not build this and you did not run round 1. READ-ONLY: never edit, create,
commit or delete a tracked file in any checkout; scratch and mutation copies only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\verify-09a0r2`.

Code under test: worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, head 58d5304c
(part A0 = 1cee0593..495c0af7; openapi regen 117f38dc; fix round 1 = 117f38dc..58d5304c). Read the round-1 brief
`docs/process/builder-sequence-briefs/verify-row-09a0.md` (scope: AC-1, AC-2 backend half, AC-3, AC-7; the rest
deferred to parts A1/B/C) and the fix brief `row-09a0-fix-1.md`.

Round 1 found (PARTIAL, no code defect): M04 (API stamps frames with its own clock) survived - the late-frame test read
at the publish time; M07 (want-key expiry), M19 (status-key expiry), M11 (foreign-user status key), M13 (`_main` skips
`prepare_process`) survived; the core test's API bypassed `LiveMarket.start`. Round 1's mutation script and list:
`...\scratchpad\verify-09a0-mt\mutate.py`, `mutants.jsonl` - re-run ALL 22 on the new head, then write at least 5 NEW
mutants of your own in `feed_bus.py` / `feed_main.py` / `feed_mode.py` / `live_market.py` (e.g. the stale window
widened, the user check on ticks inverted, MAXLEN removed, the want snapshot merged instead of replaced, the mode
allow-list made a deny-list) and name the killing test of each.

Also check: any product-code change in the fix round (the brief allowed one only if a new test proved a defect); clock
tests use the fake clock (no sleep); the core test still passes through `LiveMarket.start` with `FEED_MODE=bus`.

Known failing, not this build: `tests/test_edit_lint_hook.py::test_real_eslint_run_flags_unused_variable`,
`tests_app/test_broker_status_route.py::test_core_proof_a_stored_session_reads_connected_and_ending_it_reads_disconnected`;
locally with `OFO_REQUIRE_DB_TESTS=1` and no Redis the Redis tests ERROR by design - run them with REDIS_URL at the
stand-in (`...\scratchpad\fr`, F-58). DB runs through
`python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini <files>`,
started FIRST in the background with `-o faulthandler_timeout=60` (R16).

Why Opus: Tier A (live-data liveness across a process boundary).

Return a JSON array, one object per in-scope AC (AC-1, AC-2, AC-3, AC-7): `{"row": 9, "req": "REQ-113", "ac": "AC-n",
"result": "pass" | "fail" | "partial", "commands": "...", "observed": "... file:line", "attack": "..."}`, then under
250 words: each fail/partial with severity (CRITICAL / MAJOR / MINOR) and the smallest fix, and anything not checked.
Stop every background process you start before you report.
Budget: 40 min wall-clock, 70 tool calls
Report: evidence-table
