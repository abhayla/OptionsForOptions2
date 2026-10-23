# Row 9 part A1: REQ-113 feed process (W-137) - login, Disconnect and reconnect reach the feed; bus loss recovers honestly

Common brief: docs/process/builder-brief.md (Budget hard stop: at 64 calls start nothing new, leave the tree
consistent, commit, report; scratch-copy mutations; fix lint as you go; R13-R16).
Size: M, 7 files, 5 items
CI: app job `api` step (`tests_app/test_feed_control.py` (new), `tests_app/test_bus_socket.py`,
`tests_app/test_feed_restart_core.py`, `tests_app/test_broker_disconnect.py`, `tests_app/test_live_login_pickup.py`,
`tests_app/test_reconnect_positions_read.py`; vars: TEST_DATABASE_URL, OFO_REQUIRE_DB_TESTS=1, BROKER_TOKEN_KEY,
REDIS_URL from the `redis:7` service) - locally with REDIS_URL at the pure-Python stand-in (F-58), through
`python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini <files>`.
Expected (orchestrator, before dispatch 22:45 IST): build 60 min / ~170k; verify 20 min / ~170k; part A1 ~90 min / ~350k.

Core: in `bus` mode, Disconnect stops the FEED process's Kite socket (today only the API's BusSocket stops and the feed
keeps streaming on the old session - `broker_status.py:134` says "the socket must not keep streaming on it").
Proof: step 1 is `tests_app/test_feed_control.py` failing first: feed process + API in `bus` mode on the recorded frames
(`tests/fixtures/kite_ws/frames-2026-10-08-092000-10s.bin.gz`, the A0 launcher); call the Disconnect route; the feed's
status shows 0 live connections within the control window and no frame newer than the Disconnect reaches the API.

Spec basis: REQ-113 AC-3: "the bus holds no state that cannot be rebuilt. After a bus loss, every consumer marks its data
stale (ADR-015) until a fresh tick or a fresh Zerodha read arrives." REQ-113 AC-7: "The process holds Kite tokens only in
memory, loaded from the encrypted token store (REQ-015)". REQ-015 AC-5 (positions re-read after a reconnect; built at
row 2, `live_market.py:170-188`). ADR-053 (per-user feed).
Copy from: none beyond the map rows below.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1` (head = after A0 closes;
`git log --oneline -3` first). Commit with `git add <paths>` (never `-A`); do NOT push. Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\row09a1`.

## What to build (orchestrator decisions, technical; from the independent Opus design review of row 9)
1. The encrypted token store is the TRUTH; a control message is only a wake-up. Control stream
   `ofo:feed:<user_ref>:control` (API -> feed) carries `{kind: login | disconnect, at, user_ref}` - NEVER a token or a
   fingerprint. On any control message AND on a fixed re-check interval (so a lost message is rebuilt, AC-3), the feed
   reads the stored session: no session -> stop its KiteSocket, publish phase "stopped", do not reconnect; a session
   whose fingerprint differs from the running one -> stop the old socket, start one on the new session (memory only,
   AC-7); the same session -> nothing.
2. In `bus` mode, `LiveMarket.pick_up_login` and `stop_current` (`live_market.py:193`, `:296`) publish the control
   message in addition to their current local work. Callers (R15, each named in your report and covered by a test):
   `routes/broker.py:270` (login callback), `routes/broker_status.py:134` (Disconnect), `routes/broker_status.py:125`
   (`feed_phase` in bus mode reads the status key's phase), `routes/execute.py:192` (`latest_depth` - check frames over
   the bus still carry full-mode depth), `current_session` / `owner_margin_client` (`live_market.py:311-332`, unchanged:
   the API reads its own store).
3. Reconnect: when the feed's KiteSocket re-connects (`kite_ws.py:132`, `connections >= 2`), the feed publishes a
   `reconnected` event on the ticks stream; `BusSocket` calls the API's `_read_positions_once` exactly once per event
   (REQ-015 AC-5, the REST read stays in the API through the egress gate).
4. Bus loss recovery (AC-3): after Redis returns, the API's quotes stay stale until a frame whose FEED receive time is
   after the loss (no backlog replay); on the feed side, a failed `want` read keeps the last known set (a read failure
   is not an expiry) and status publishing resumes.

5. Close part A0's verify-round-2 gaps (no code defect; tests and one bound): a test asserting
   `WANT_REFRESH_S*1000 < WANT_TTL_MS` and `STATUS_EVERY_S*1000 < STATUS_TTL_MS` (kills N12, N05a); a status saying
   `connected: false` reads as not connected (N07); an oversized frame in the malformed-message test (N11); the relay's
   "ended" status (N13); the stream-length cap (N02); bound the test that HANGS under mutant M18 (find it; a hung CI
   job is a defect) - the round-2 scripts and results are in
   `...\scratchpad\verify-09a0r2\` (`mutate_r2*.py`, `summary.txt`). Re-run those mutants: each red within 120 s.

Attack list: (each names its test file)
1. Disconnect in `bus` mode -> the feed's Kite socket closes and no later frame reaches the API (`tests_app/test_feed_control.py`).
2. The control message is lost (never published) -> the feed's re-check still stops within the interval (same file).
3. A new login (different session) -> the feed restarts on it; the same session again -> no restart (same file).
4. No token or fingerprint in any control or event message or log line (same file).
5. A re-connect -> exactly one positions read in the API; a second identical event id -> no second read
   (`tests_app/test_reconnect_positions_read.py`).
6. Redis lost then back -> stale until a frame received after the loss; the feed keeps its subscriptions through the
   outage (`tests_app/test_bus_socket.py`).
7. `inprocess` mode behaviour unchanged: Disconnect, login pick-up and the positions re-read tests still pass
   (`tests_app/test_broker_disconnect.py`, `tests_app/test_live_login_pickup.py`).

Standing items: (a) n/a: the re-check interval is a fixed small timer, not a budgeted job; (b) n/a: no CI step changes; (c) n/a: no static detector; (d) the token store's answer states - session present, absent, unreadable (decrypt error), DB unreachable - and Redis's (control stream empty, malformed message, connection refused/dropped): each listed in `tests_app/test_feed_control.py` with what it does (unreadable or unreachable -> keep the current socket and log the class only; absent -> stop).
Threat model: in scope - a socket streaming on a session the owner disconnected, a token or fingerprint on the bus or in a log, a lost control message leaving the feed on an old session, a double positions read; out of scope - a hostile local process writing to Redis.
Findings checked: caller-supplied-verdict-trusted, wall-clock-assertion-flakes-under-load, dependent-tests-not-run-stale-later
Reviewer checklist: the store, not the message, decides; every caller of pick_up_login / stop_current / feed_phase /
latest_depth named and tested; each guard deleted in a scratch copy has a killing test; fake clock, no sleep; R16
timing; no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only;
no regenerated files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Legacy map rows (copy_from_check.py)
Rows of the legacy-reuse map that name this brief's requirements. Act on each:
COPY/ADAPT -> use it (provenance header) or write in the report why not; REFERENCE -> read
before designing; SKIP -> do not re-survey.

| `market_data/auth_tracking.py` (102) | REFERENCE | token-expiry detection idea | REQ-015 |
| `app/api/routes/auth.py:60-175` | REFERENCE | row 9; token stored only via the secure mechanism | REQ-015 |
| `src/components/settings/KiteSettings.vue` (388), `views/AuthCallbackView.vue` (81) | ADAPT (P4) | no token in URL | REQ-015 |
