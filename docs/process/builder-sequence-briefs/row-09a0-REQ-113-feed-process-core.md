# Row 9 part A0: REQ-113 price feed in its own process (W-137) - the core: an API restart does not cut the feed

Common brief: docs/process/builder-brief.md (Budget hard stop: at 64 calls start nothing new, leave the tree
consistent, commit, report; scratch-copy mutations; fix lint as you go; R13).
Size: M, 12 files, 4 items
CI: app job `api` step (`tests_app/test_feed_restart_core.py`, `tests_app/test_bus_socket.py`,
`tests_app/test_feed_process_boundary.py`, `tests_app/test_live_market_refuses_test_db.py`; vars: TEST_DATABASE_URL,
TEST_ADMIN_DATABASE_URL, OFO_REQUIRE_DB_TESTS=1, BROKER_TOKEN_KEY, the KITE_* placeholders, and NEW `REDIS_URL` from a
`redis:7` service you add to the `api` job of `.github/workflows/app-tests.yml` - edit it with the Edit tool only);
locally the same files run with `REDIS_URL` pointing at the pure-Python stand-in (F-58) started by a test fixture, through
`python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini <files>`.
A test that needs Redis and finds none FAILS when `OFO_REQUIRE_DB_TESTS=1` (CI) - never a silent skip there.
Expected (orchestrator, before dispatch): build 60 min / ~170k tokens; verify 20 min / ~170k; part A0 total ~90 min /
~350k. Row 9 = parts A0, A1, B, C (independent Opus design review 2026-10-22: ADOPT WITH CHANGES).

Core: the market-data process holds the Kite price socket; restarting the API process does not reconnect it, and
fresh frames reach the restarted API.
Proof: step 1 is `tests_app/test_feed_restart_core.py` failing first: a looping fake Kite websocket server on loopback
(port 0) replays the REAL recorded frames `tests/fixtures/kite_ws/frames-2026-10-08-092000-10s.bin.gz` (in a loop, so
frames keep coming past the restart); the feed process (the REAL `KiteSocket`) and the API process start as
subprocesses through a test-only launcher; the API is killed and restarted; the feed's published status shows
`connections` == 1 throughout and frames received by the NEW API process are newer than the restart.

Spec basis: REQ-113 AC-1: "The market-data process owns every user's Kite price socket and order-update stream; the API
process opens none." REQ-113 AC-2: "Restarting or redeploying the API process does not close any user's Kite socket".
REQ-113 AC-3: "While there is one process, no bus or Redis is added." REQ-113 AC-7: "The process holds Kite tokens only
in memory, loaded from the encrypted token store (REQ-015)". ADR-043 (Redis in the stack). ADR-015 (an old price is
never shown as live). Order-update stream parts: deferred (order path, table's deferred list).
Copy from: none beyond the map rows below - legacy `OFO` WebSocket + Redis pattern is REFERENCE only.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1` (head = after row 8 closes;
`git log --oneline -3` first). Commit with `git add <paths>` (never `-A`); do NOT push. Use the edit tools. Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\row09a0`.
The stand-in is already installed there for a look: `...\scratchpad\fr` (fakeredis 2.40.0, redis 6.4.0); pin
`redis==6.4.0` in `requirements-app.txt` and `fakeredis==2.40.0` in the dev/test requirements file.

## What to build (orchestrator decisions, technical, recorded; design review accepted)
1. Feed mode, an allow-list of two values in config: `inprocess` (today: the API holds the socket; no bus - AC-3's
   one-process case; the e2e replay `OUTCOME_REPLAY=1` stays here; REFUSED at startup when `APP_ENV=production`) and
   `bus` (the API opens no Kite socket; a separate process does). Any other value refuses startup.
2. `backend/ofo_app/feed_main.py`: the market-data process. Reuses `LiveMarket` + the REAL `KiteSocket` unchanged; loads
   the token from the encrypted store (memory only); installs the egress gate exactly as `create_app` does
   (`main.py:89`) BEFORE any Kite call; checks its DB pool against the role budget (`verify_pool_budget`, `main.py:63`).
3. The bus (Redis Streams, F-58 - NOT pub/sub): feed -> API: stream `ofo:feed:<user_ref>:ticks` (XADD with a MAXLEN cap)
   carrying the raw frame bytes plus the time the FEED received it, and connect / drop / session-ended events; API -> feed:
   key `ofo:feed:<user_ref>:want` = the FULL timed set of wanted instrument tokens with an expiry (a snapshot, never
   add/remove deltas; an expired key = nothing wanted); feed status key `ofo:feed:<user_ref>:status` with an expiry
   (connections, last frame time, feed phase). Every message carries the user ref. Blocking reads in short loops (<= 200
   ms) so the stand-in's coarse timer does not add seconds.
4. `BusSocket` in the API with the same `run` / `stop` / `connections` interface as `KiteSocket`, swapped in at
   `live_market.py:161` in `bus` mode: it feeds the raw frames and events into the SAME provider methods
   (`kite_provider.py:72, 138-144`) so there is one frame parser and `latest_depth` keeps working; frames are stamped
   with the feed's receive time, not the API's arrival time; a lost Redis connection calls `on_disconnected` (stale,
   ADR-015). `FanOut.subscribe` (`live_push.py:116`) changes are written into the `want` snapshot.
   Test-only launcher under `tests_app/` that enters test mode in the child (egress `_enter_test_mode`, loopback Kite
   URL allowed only there, `kite_http.py:88-91`); NEVER an environment switch in production code. Use plain
   `subprocess.Popen` from a sync fixture (the selector loop cannot run asyncio subprocesses on Windows, `main.py:60`);
   ports bound to 0 and passed in; readiness by polling the status key, never `sleep`; assert the same on Windows and
   Ubuntu (Windows `terminate()` is a hard kill).
Out of this part (parts A1, B, C): login/Disconnect control messages over the bus, Redis-loss proofs beyond
`on_disconnected`, per-user socket map, caps refuse-and-log, 06:00 session end, the browser "reconnecting" state.

Attack list: (each names its test file)
1. API startup in `bus` mode opens no websocket and makes no Kite call (`tests_app/test_feed_process_boundary.py`).
2. `inprocess` mode with `APP_ENV=production`, or an unknown mode, refuses startup (same file).
3. API restart: the feed's `connections` never exceeds 1 and frames after the restart reach the new API
   (`tests_app/test_feed_restart_core.py`).
4. A frame published late (feed receive time older than the stale window) is never shown as live
   (`tests_app/test_bus_socket.py`).
5. Redis connection lost -> the API's quotes read stale, not live (`tests_app/test_bus_socket.py`).
6. The `want` key expires -> the feed unsubscribes those tokens; a restarted API rebuilds it from its own screens
   (`tests_app/test_bus_socket.py`).
7. `feed_main` started without the test launcher refuses a loopback Kite URL and has the egress gate installed; no
   token appears in any bus message or log line (`tests_app/test_feed_process_boundary.py`).
8. `feed_main` refuses the test database exactly like the API (`tests_app/test_live_market_refuses_test_db.py`).

Standing items: (a) n/a: no time-budgeted job (the feed loop is event driven); (b) the CI `api` step gains the `redis` import: the dependency install step runs before it (requirements-app.txt) - check the step order; (c) n/a: no static detector added; (d) Redis answer states - value present, key expired/absent, connection refused, connection dropped mid-read, empty stream, malformed message: each listed in `tests_app/test_bus_socket.py` with what it does (stale or refuse, never live).
Threat model: in scope - one user's frames read by another user's consumer, an old frame shown as live, a token on the bus or in a log, a Kite call outside the egress gate, a test switch reachable in production; out of scope - a hostile process on the same host writing to Redis (Redis is bound to localhost).
Findings checked: wall-clock-assertion-flakes-under-load, dependent-tests-not-run-stale-later, caller-supplied-verdict-trusted
Reviewer checklist: the core test runs the REAL KiteSocket against the recorded frames across a real API process
restart; modes are an allow-list; no production env switch for test mode; feed receive time on every frame; every
Redis answer state tested; egress gate in the feed process; R13 selection run and listed; no new duplicated literal;
reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR.

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
