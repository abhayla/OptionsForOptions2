# Verifier brief: builder sequence row 9 parts A1 + C (REQ-113 / W-137), Tier A, round 1 (one shared verifier)

Independent, adversarial verifier; you did not build either part. READ-ONLY: never edit, create, commit or delete a
tracked file in any checkout; scratch and mutation copies only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\verify-09a1c`.

Code under test: worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, head <HEAD>.
Part C (frontend) = commit f6a6bc5e; part A1 (backend + tests_app) = commit 6a0f7117. Briefs:
`docs/process/builder-sequence-briefs/row-09a1-REQ-113-feed-control.md` and `row-09c-REQ-113-browser-reconnect.md` -
run every item of both `Attack list:` sections. Spec: `spec/requirements/REQ-113.md` - for A1: AC-3 (bus loss, rebuildable
state) and AC-7 (tokens only in memory from the store), plus REQ-015 AC-5 (one positions read after a reconnect); for C:
AC-2's browser half ("reconnecting", resume within 10 s, never an old price as live). Part A0 is verified (AC-1, AC-2
backend half, AC-7 pass); part B is not built yet.

A1 attack first: (1) Disconnect in `bus` mode really closes the FEED's Kite socket - and a lost control message is
rebuilt by the re-check; (2) the token store decides, never the message: forge a `login` control message with no stored
session -> nothing starts; (3) no token or fingerprint on any stream or in any log (grep the captured logs); (4) one
positions read per reconnect event - the event id is the event TIME: two genuine reconnects in the same second, and a
replayed event, each give the right count; (5) after a Redis outage no frame received before the outage is shown live;
(6) `inprocess` mode unchanged; (7) delete each A1 guard in a scratch copy (store re-check, control handling, event
dedupe, pre-outage frame drop, want-keep on read failure) and name the killing test.

C attack first: (1) the socket helper's timing: exactly 30 attempts 1 s apart, then 2, 4, 8, 16, 30 s, give-up after 10
slow attempts - vitest with fake timers; (2) `useIndexLive.js` was rewritten onto `createLiveSocket` "read-only form" -
check it never sends a body, never shows live without an answer push, and that the index strip and index page behave
as before when healthy (their existing tests and e2e `index-view.spec.ts`); (3) a push delivered late on a dropped socket
is never shown live; (4) every live screen (StrategyBuilderPage, LiveStrategyCard, ExecuteStrategyPage, OptionChainPage,
IndexViewPage, IndexStrip) shows `live-reconnecting` from the ONE constant; (5) delete each C guard in a scratch copy
(the marker reset on close, the answer-only live, the fast phase) and name the killing test; (6) run `npm run lint` and
`npm run test:run` in `frontend/` (CI runs those two; `format:check` is not a CI step and fails on main too - ignore it)
and the e2e `npx playwright test e2e/feed-reconnect.spec.ts e2e/index-view.spec.ts e2e/strategy-live.spec.ts` against a
local `vite preview` if you can start it (stop it after).

Known failing, not this build: `tests/test_edit_lint_hook.py::test_real_eslint_run_flags_unused_variable`,
`tests_app/test_broker_status_route.py::test_core_proof_a_stored_session_reads_connected_and_ending_it_reads_disconnected`;
`frontend/tests/learn.test.js` (a CRLF line end on this Windows checkout). Redis tests run on the stand-in (F-58;
`fakeredis==2.40.0` is installed); DB runs through
`python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini <files>`,
started FIRST in the background with `-o faulthandler_timeout=60` (R16). Stop every process you start.

Why Opus: Tier A (live-data liveness: a Disconnect that keeps streaming, or an old price shown live in the browser).

Return a JSON array, one object per AC: `{"row": 9, "req": "REQ-113", "part": "A1" | "C", "ac": "AC-n", "result":
"pass" | "fail" | "partial", "commands": "...", "observed": "... file:line", "attack": "..."}` (REQ-015 AC-5 as
`"req": "REQ-015"`), then under 250 words: each fail/partial with severity (CRITICAL / MAJOR / MINOR) and the smallest
fix, and anything not checked.
Budget: 40 min wall-clock, 70 tool calls
Report: evidence-table
