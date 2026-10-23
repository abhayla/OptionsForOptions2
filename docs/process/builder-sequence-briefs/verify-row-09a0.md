# Verifier brief: builder sequence row 9 part A0 (REQ-113 feed process core / W-137), Tier A, round 1

Independent, adversarial verifier; you did not build this. READ-ONLY: never edit, create, commit or delete a tracked
file in any checkout (no in-place mutation); scratch and mutation copies only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\verify-09a0`.

Code under test: worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, head
117f38dc (part A0 = 1cee0593..495c0af7; 117f38dc only regenerates `docs/api/openapi.json` for a row-7 label). Spec:
`spec/requirements/REQ-113.md`; in scope for A0: AC-1 (price socket part), AC-2 (backend half: API restart does not
reconnect the feed's socket), AC-3 (the bus: Redis, rebuildable state, stale on bus loss), AC-7. AC-4, AC-5 order parts,
AC-6, AC-8, AC-9 and the browser half of AC-2 belong to later parts (A1, B, C) - report them `deferred`. ADR-015,
ADR-043, ADR-053, F-58 in `spec/findings.md`. Builder brief:
`docs/process/builder-sequence-briefs/row-09a0-REQ-113-feed-process-core.md` - run every item of its `Attack list:`.

The builder reported, unproved: (1) the core test `tests_app/test_feed_restart_core.py` was written AFTER the code and
was never seen failing - make it fail in a scratch copy (e.g. the API process opening its own socket in `bus` mode, or
the feed reconnecting on an API restart) and name what goes red; (2) NO mutations were run - delete each guard in
`feed_mode.py`, `feed_bus.py`, `feed_main.py` (mode allow-list, production refusal, feed receive time, stale on Redis
loss, `want` expiry, user ref on every message, egress gate install, test-DB refusal) in scratch copies and name the
killing test for each; (3) all Redis tests ran on the pure-Python stand-in (F-58), never on real Redis - say so; CI's
`redis:7` service runs them at the chunk PR (read the `api` job of `.github/workflows/app-tests.yml` with Read: does
the service exist, is `REDIS_URL` set, does a missing Redis FAIL there instead of skip?); (4) deviation: `inprocess` is
refused under `APP_ENV=production` only when `LIVE_MARKET` is on - judge it (is any socket possible with LIVE_MARKET
off?); (5) deviation: in `bus` mode the positions re-read after a reconnect and the login / Disconnect control are not
carried yet - check that `inprocess` (the default) is unchanged and that nothing selects `bus` by default.

Also attack: a frame from user A's stream read by a consumer for user B; an old frame (feed receive time older than the
stale window) shown live; a token or token fingerprint in any bus message or log line; a Kite call from `feed_main`
outside the egress gate; a test-only switch reachable from production code; Redis answer states (absent key, expired,
refused, dropped mid-read, empty stream, malformed message) - each ends stale or refused, never live.

Known failing, not this build: `tests/test_edit_lint_hook.py::test_real_eslint_run_flags_unused_variable` (local
ESLint) and `tests_app/test_broker_status_route.py::test_core_proof_a_stored_session_reads_connected_and_ending_it_reads_disconnected`
(fails on main too, clock skew). DB tests through the throwaway-database runner, started FIRST in the background with
`-o faulthandler_timeout=60` (R16; ~23 s per DB test over the tunnel):
`python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini <files>`.
Run at least the four new files, `tests_app/test_live_market_refuses_test_db.py`, `tests_app/test_live_login_pickup.py`,
`tests_app/test_strategy_live_push.py`, `tests_app/test_kite_ws.py` and every file importing `live_market` (grep).

Why Opus: Tier A (live-data liveness: a process boundary that, if wrong, shows an old price as live or cuts every
user's feed on a deploy).

Return a JSON array, one object per AC: `{"row": 9, "req": "REQ-113", "ac": "AC-n", "result": "pass" | "fail" |
"partial" | "deferred", "commands": "...", "observed": "... file:line", "attack": "..."}`, then under 250 words: each
fail/partial with severity (CRITICAL / MAJOR / MINOR) and the smallest fix, and anything not checked and why. Stop
every background process you start before you report.
Budget: 40 min wall-clock, 70 tool calls
Report: evidence-table
