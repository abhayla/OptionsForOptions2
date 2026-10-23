# Row 9 part B: REQ-113 (W-137) - one socket per user in the feed process, Zerodha's caps, the 06:00 end, isolation

Common brief: docs/process/builder-brief.md (Budget hard stop: at 64 calls start nothing new, leave the tree
consistent, commit, report; scratch-copy mutations; fix lint as you go; R13-R16).
Size: M, 9 files, 6 items
CI: app job `api` step (`tests_app/test_feed_user_isolation.py`, `tests_app/test_feed_caps.py`,
`tests_app/test_feed_session_expiry.py` (new), `tests_app/test_kite_ws.py`, `tests_app/test_bus_socket.py`,
`tests_app/test_feed_restart_core.py`; vars: TEST_DATABASE_URL, OFO_REQUIRE_DB_TESTS=1, BROKER_TOKEN_KEY, REDIS_URL from
the `redis:7` service) - locally with REDIS_URL at the pure-Python stand-in (F-58), through
`python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini <files>`.
Expected (orchestrator, before dispatch): build 60 min / ~170k; verify 20 min / ~170k; part B ~90 min / ~350k.

Core: in the feed process, killing user A's Kite socket leaves user B's ticks flowing (AC-9).
Proof: step 1 is `tests_app/test_feed_user_isolation.py` failing first: two users with stored sessions in the throwaway
database, two looping fake Kite servers on loopback replaying the REAL recorded frames
(`tests/fixtures/kite_ws/frames-2026-10-08-092000-10s.bin.gz`), the feed process through the A0 launcher; user A's
fake server is killed; user B's API consumer keeps receiving frames newer than the kill, and no frame of A's reaches B.

Spec basis: REQ-113 AC-6: "The market-data process respects Kite's per-connection instrument cap and per-key connection
cap as Zerodha states them at build (held as configuration with source and date, never typed from memory); a
subscription beyond the cap is refused and logged, never silently dropped." REQ-113 AC-8: "At the daily 06:00 session
expiry (ADR-053) the process closes that user's sockets, publishes "session ended" for the user, and does not try to
reconnect them". REQ-113 AC-9: "One user's socket failure does not affect another user's socket". ADR-053 (per-user
feeds in V1). F-57 (3000 instruments per connection; 3 connections per API key, from the Kite docs, 2026-10-22).
Copy from: none beyond the map rows below.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1` (head = after part A1 closes).
Commit with `git add <paths>` (never `-A`); do NOT push. Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\row09b`.

## What to build (orchestrator decisions, technical, recorded)
0. DONE by the orchestrator (F-59, ADR-170) - skip the research; for the record, the question was: read Zerodha's websocket page (https://kite.trade/docs/connect/v3/websocket/)
   and, if it is unclear, the Kite forum, for ONE question: is "3 connections per API key" counted per api_key across
   ALL users of one app, or per api_key per user's access token? Report the exact sentence and URL. Do not decide on it:
   the orchestrator records it as finding F-59 (if it is per app, per-user feeds cap at 3 users - an owner question
   about ADR-053's scale). Build the cap as configuration either way.
1. Per-user sockets: the feed process holds a map `user_ref -> (KiteSocket, task)`, built from the active sessions in
   the token store (`broker_token_store.py`; a new read of the active user refs - an allow-list query returning
   user_ref only, never a token); each socket runs in its own task with its own error handling, so one socket's
   exception, close or reconnect never touches another (AC-9). Today only the owner has a session; the map must still
   be per user.
2. Caps as configuration with source and date (AC-6): per-connection instruments (3000) and per-key connections (3),
   each with the F-57 URL and 2026-10-22 beside it, in ONE home (`order_limits_registry.py:47-48` already registers the
   3000 - extend that registry, do not retype). A subscription beyond the per-connection cap is REFUSED and logged (class
   and count, never the token), never truncated (`kite_ws.py:175-177` truncates and counts today); a socket beyond the
   per-key cap is refused and logged; the user's status key says "capped" so the API shows it.
3. 06:00 session end (AC-8): at the session's expiry (per ADR-053 the store already ends an EXPIRED session,
   at `broker_token_store.py:104`) the feed closes that user's socket, publishes the session-ended event on that user's stream and
   status, and does not reconnect; the API shows "Monitoring paused - reconnect Zerodha" for that user's strategies
   through the existing session-ended path (`SESSION_ENDED`, `kite_ws.py:58`). Clock: the injected clock, never sleep.

4. A feed started with NO stored session (e.g. a box restart at 05:00, before any login) installs the egress gate,
   then IDLES and waits for a login control message or the re-check - it no longer exits with code 3 (a process
   manager would restart an exiting feed in a loop until a login). Update the A0 boundary test that pins exit 3: it now
   asserts gate installed first, no Kite call, still running, and a later stored session starts a socket.

5. From the A1 verify (MINOR): `supervise`'s FIRST `xrevrange` call has no RedisError handling, so a feed started
   while Redis is down crashes; catch it there, start from "0-0", log the class only, keep retrying on the re-check
   (test: Redis refused at feed start -> the process stays up and starts once Redis answers).
Decision for item 0 is now taken (ADR-170, owner 2026-10-23): per-user feeds stay; the cap stays 3 per key as
configuration; a 4th connection is refused and logged, and that user's screens say live prices are not available.

Attack list: (each names its test file)
1. Kill user A's socket -> B's ticks continue; A's frames never reach B (`tests_app/test_feed_user_isolation.py`).
2. An exception inside A's frame handling -> B's socket and task untouched (same file).
3. 3001 instruments for one connection -> refused and logged with the count, none silently dropped; the user's status
   says capped (`tests_app/test_feed_caps.py`).
4. A 4th connection on one key -> refused and logged (same file).
5. 06:00 expiry -> that user's socket closed, "session ended" published, no reconnect for 10 minutes of fake clock;
   another user's socket unaffected (`tests_app/test_feed_session_expiry.py`).
6. The active-users query returns user refs only (an allow-list of columns) and no token reaches a log or the bus
   (`tests_app/test_feed_user_isolation.py`).
7. The existing truncation test in `tests_app/test_kite_ws.py` is updated to the refusal (grep `over_limit`).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes; (c) n/a: no static detector; (d) the token store's answer states for the active-users read and per-user token - present, none, expired at read, undecryptable, DB unreachable - and Kite's socket answers - accepted, refused, 403 session ended, dropped - each listed in `tests_app/test_feed_user_isolation.py` or `test_feed_session_expiry.py` with what it does.
Threat model: in scope - user A's frames or status reaching user B, one user's failure stopping another's feed, a silent cap drop, a reconnect on an ended session, a token in a log or on the bus; out of scope - a hostile local process writing to Redis.
Findings checked: guard-as-forbidden-list, caller-supplied-verdict-trusted, wall-clock-assertion-flakes-under-load
Reviewer checklist: per-user tasks isolated (an exception test); caps from one registry with source + date; refusal not
truncation; 06:00 on the injected clock; the active-users query is an allow-list; every caller of the changed socket
and registry named (R15); R16 timing; no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not
rise; targeted tests only; no regenerated files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table
