# W-1xx: Market-data process separate from the API, with an internal bus (REQ-113)

Common brief: docs/process/builder-brief.md (read it first; this file is the item part only).

Core: the process that owns every user's Kite socket keeps its sockets, counters and last-message time through an API restart.
Proof: start the market-data process and the API as two OS processes against the recorded replay, restart only the API, and read the socket's connection count and last-message time unchanged; browser websocket reconnects to the new API and shows a tick within 10 s. Live window: the same with the owner's real Kite session.

Tier: A (live feed; per-user data separation; token handling)

Spec basis:
REQ-113 AC-1: "The market-data process owns every user's Kite price socket and order-update stream; the API process opens none."
REQ-113 AC-2: "Restarting or redeploying the API process does not close any user's Kite socket"
REQ-113 AC-3: "While there is one process, no bus or Redis is added."
REQ-113 AC-5: "Each user's data stays that user's (ADR-053)"
REQ-113 AC-6: "The market-data process respects Kite's per-connection instrument cap and per-key connection cap"
REQ-113 AC-8: "At the daily 06:00 session expiry (ADR-053) the process closes that user's sockets"
REQ-113 AC-9: "One user's socket failure does not affect another user's socket"
REQ-048 AC-4: "Provider streams are shared and fanned out internally; there is no vendor subscription per user"
ADR-165 (8): "this scope keeps today's Kite login on the owner's Kite app (ADR-060"

Copy from: legacy-reuse.md rows 1 and 3 (ticker pool/router, KiteTicker bridge), already adapted in backend/ofo_app/live_market.py and kite_ws.py; no new copy. Reference only: algochanakya app/websocket/manager.py (row 'REFERENCE').

Sensibull screens: no Sensibull equivalent in the study (process layout is not visible from outside; ARCHITECTURE.md of the study lists services, not processes).

Multi-broker review (read D:\Abhay\Ventures\competitors\multi-broker-architecture\2026-10-21\INDEX.md first): L5 and L7 (one platform socket per user session; relay between processes: OpenAlgo ZeroMQ relay is the 'useful' pattern, apps/openalgo.md); T6 (fails open) applies: a missing user id on a bus message must drop the message, not broadcast it.

## What to build
1. New entry `python -m ofo_app.market_data_main` (backend/ofo_app/market_data_main.py): builds LiveMarket (backend/ofo_app/live_market.py:1-316) and KiteSocket, loads Kite tokens in memory only from the encrypted store (backend/ofo_app/broker_token_store.py), every Kite call through the egress door (backend/ofo/broker/egress.py) (AC-7). Uses the selector loop (ofo_app/event_loop.py).
2. API process (backend/ofo_app/main.py, routes/live.py, routes/indices.py): stops opening Kite sockets. It subscribes to the bus and fans out to browser websockets (live_push.py, index_push.py). Test: API startup opens no Kite websocket (AC-1).
3. Bus: decided in Open: technical below (Redis pub/sub, an in-memory fake for tests). Ticks and events carry the user id; a test shows user A's quote never reaches user B (AC-5). Bus loss = every consumer marks data stale (ADR-015), rebuilt from the next tick; the bus holds nothing durable (AC-3, AC-4).
4. Caps held as configuration with source and date from Kite's docs at build, not from memory (AC-6); a subscription beyond the cap is refused and logged.
5. 06:00 IST expiry: close that user's sockets, publish 'session ended', no reconnect; strategies show 'Monitoring paused - reconnect Zerodha' (AC-8). One user's socket failure isolated (AC-9).
6. Order-update stream (AC-4 second half): only the READ side. The stream only starts a reconciliation read, never a position change; nothing here places or modifies an order. Do not build the order-update consumer beyond publishing the event to the bus; REQ-103 AC-4 (lane C import brief) consumes it.

## AC status (main plus open PRs, 2026-10-21)
| AC | Status | Where |
|---|---|---|
| 113 AC-1 | missing | sockets are opened in-process (live_market.py) |
| 113 AC-2 | missing | |
| 113 AC-3 | missing | no Redis in requirements-app.txt (grep returned nothing) |
| 113 AC-4 | partial | reconciliation reads exist (backend/ofo/reconciliation/triggers.py:91) |
| 113 AC-5 | partial | live_market.py keys by session; no bus |
| 113 AC-6 | missing | kite_ws.py:3 states 3,000 tokens/connection; per-key cap not held as config |
| 113 AC-7 | partial | egress door exists (backend/ofo/broker/egress.py) |
| 113 AC-8 | missing | session.py expire_on_clock exists; no socket close on expiry |
| 113 AC-9 | missing | |
| 048 AC-4/AC-5 | exists (partial) | fanout.py:35 FanOut; check no browser holds vendor credentials |

## Every answer state of each outside system
Bus (Redis): reachable (stated) = publish; down at start (failed) = market-data process keeps its sockets, API shows data stale, retries with backoff; message lost (absent) = consumer marks stale; malformed message (ambiguous) = dropped and counted, never decoded into a quote. Kite: as in C1. Database: token store unreadable (failed) = that user's socket not opened, 'Monitoring paused - reconnect Zerodha'; no row (not found) = same. Two market-data processes started (ambiguous) = second one refuses to start (single owner lock in the database, owner recorded per run-discipline E2).

## Attack cases (reviewer: hands-on first)
- Start the API with the market-data process stopped: API serves 'data stale', opens no socket.
- Kill the market-data process: browsers show reconnecting then stale, API stays up.
- Publish a tick for user A on the bus with a forged user id for B: B's websocket must not get it.
- Bus message with a float price: refused (money is Decimal as a string, ADR-008).
- 3,001st subscription: refused and logged, the other 3,000 unaffected.
- Token appears in a bus message or log: test fails.

Threat model: in scope: cross-user leakage over the bus, API restart, bus loss, token handling; out of scope: Redis compromise, many-user load (launch scope).

Findings checked: live-subscription-lost-on-release-reacquire, liveness-from-shared-subscribers, shared-inflight-marker-without-owner, live-work-shares-test-database, secret-filter-by-key-name, db-role-connection-limit-below-pool-size, db-role-limit-below-pool-size

Standing items: (a) applies: any periodic task in the market-data process (cap check, heartbeat publish) uses a small fixed share, never the whole loop; a test shows tick handling still runs. (b) applies: if redis is added to requirements-app.txt, the CI step that imports it runs after the install step. (c) applies: the 'API opens no Kite socket' scan names the socket class by import source (ofo_app.kite_ws), fails closed on re-exports, renames and same-named local classes. (d) applies: states above.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Targeted tests: tests_app/test_market_data_process.py (new), tests_app/test_live_push*.py, tests_app/test_index_*.py, tests_app/test_egress_gate_doors.py, tests/test_egress_gate.py
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (the one exception: a changed API model regenerates docs/api/openapi.json and is registered in tests_app/test_response_door.py, per builder-brief.md).
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Open
Open: technical: bus choice. REQ-113 AC-3 names Redis (ADR-043) once two processes run, and redis is not in requirements-app.txt. Proposal: Redis pub/sub via redis-py with an in-memory fake for unit tests; add `redis` to requirements-app.txt in this PR (project file, not a kit file); the app-tests CI job needs a redis service container (workflow is project-owned: .github/workflows/app-tests.yml). Fall back to a PostgreSQL LISTEN/NOTIFY bus only if the CI service cannot be added.
Open: technical: depends on C1 (health states) merging first; stacked PR.
Open: business: none. Live window needed for AC-2 and AC-8 (owner Kite login).

## Legacy map rows (copy_from_check.py)
Rows of spec/technical-design/legacy-reuse.md that name this brief's requirements. Act on each:
COPY/ADAPT -> use it (provenance header) or write in the report why not; REFERENCE -> read before
designing; SKIP -> do not re-survey.

| `ticker/adapter_base.py` (273), `ticker/router.py` (377) | ADAPT | row 1; router gets auth + entitlement checks | REQ-048 |
| `market_data/market_data_base.py` (520) | ADAPT | trim to Zerodha, behind our gateway | REQ-048 |
| `market_data/kite_adapter.py` (440) | ADAPT | user's own session token only, server-side | REQ-048, REQ-053 |
| `src/composables/autopilot/useWebSocket.js` (505) + test (832) | ADAPT (P3b) | token off the query string (`:53`); decouple from autopilot | REQ-043, REQ-048 |
