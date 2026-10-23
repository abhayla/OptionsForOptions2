# Verifier brief: builder sequence row 9 FINAL (REQ-113 price socket part / W-137), Tier A, every in-scope AC

Independent, adversarial verifier; you did not build any part of row 9 and you did not verify parts A0, A1 or C.
READ-ONLY: never edit, create, commit or delete a tracked file in any checkout; scratch and mutation copies only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\verify-09final`.

Code under test: worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, head <HEAD>.
Row 9 = 1cee0593..<HEAD>: A0 495c0af7 + fix 58d5304c; A1 6a0f7117; C f6a6bc5e + fix 4bcea64e; B 9dd50d9b + finish 05124939, d9332fe3 + finish-2 8ff10625. Briefs (run
every `Attack list:` item of B again, and spot-check A0/A1/C): `docs/process/builder-sequence-briefs/row-09a0-*.md`,
`row-09a1-*.md`, `row-09b-*.md`, `row-09c-*.md`. Earlier verifier briefs (what was already checked):
`verify-row-09a0.md`, `verify-row-09a0-r2.md`, `verify-row-09a1c.md`. Spec: `spec/requirements/REQ-113.md` (every AC),
ADR-015, ADR-043, ADR-053, ADR-170, F-57, F-58, F-59.

Scope: AC-1, AC-2 (backend and browser halves), AC-3, AC-6, AC-7, AC-8, AC-9: pass / fail / partial each. AC-4 and the
order-update parts of AC-1 and AC-5 are deferred (order path, the table's deferred list): report them `deferred`; AC-5's
price part (a user's quotes never reach another user) is in scope.

Attack first (part B is new): (1) kill user A's socket -> B's ticks continue; an exception inside A's handling -> B
untouched; A's frames and status never reach B; (2) 3001 instruments -> refused and logged with the count, nothing
silently dropped; a 4th connection -> refused and logged; caps from ONE registry with source and date (F-57); (3) 06:00
expiry on the injected clock -> that user's socket closed, session ended published, no reconnect; another user
unaffected; (4) a feed started with no session idles (gate installed first, no Kite call) and starts when a session is
stored; a feed started while Redis is down stays up and recovers; (5) the active-users read returns user refs only; no
token in a log or on the bus; (6) delete each part-B guard in a scratch copy and name the killing test.

Then the whole row: (7) run the four feed test files plus `tests_app/test_kite_ws.py`, `test_live_market_refuses_test_db.py`,
`test_live_login_pickup.py`, `test_strategy_live_push.py`, `test_broker_disconnect.py`, `test_reconnect_positions_read.py`,
`test_feed_control.py`, the new part-B files, and every other `tests_app` file importing `live_market`, `feed_bus`,
`feed_main` or `kite_ws` (grep) through the throwaway-database runner, started FIRST in the background with
`-o faulthandler_timeout=60` (R16); (8) `npm run lint` and `npm run test:run` in `frontend/`; (9) the guard line
`python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py`
and `-m repo_scan tests`; (10) the Playwright e2e `frontend/e2e/feed-reconnect.spec.ts` if a Chromium is available
(`PW_CHROMIUM_PATH` pointing at an installed Chrome worked for the part C builder) - else say not run.

Known failing, not this build: `tests/test_edit_lint_hook.py::test_real_eslint_run_flags_unused_variable`,
`tests_app/test_broker_status_route.py::test_core_proof_a_stored_session_reads_connected_and_ending_it_reads_disconnected`,
`frontend/tests/learn.test.js` (CRLF on this checkout). Redis tests on the stand-in (F-58, `fakeredis==2.40.0`); DB runs
through `python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini <files>`.
Stop every process you start before you report.

Why Opus: Tier A (live-data liveness and per-user data isolation across a process boundary).

Return a JSON array, one object per AC: `{"row": 9, "req": "REQ-113", "ac": "AC-n", "result": "pass" | "fail" |
"partial" | "deferred", "commands": "...", "observed": "... file:line", "attack": "..."}`, then under 250 words: each
fail/partial with severity (CRITICAL / MAJOR / MINOR) and the smallest fix, and anything not checked.
Budget: 40 min wall-clock, 70 tool calls
Report: evidence-table
