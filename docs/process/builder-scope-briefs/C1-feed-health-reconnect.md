# W-1xx: Live feed health check, silence reconnect and jittered backoff (REQ-114, REQ-133 AC-3)

Common brief: docs/process/builder-brief.md (read it first; this file is the item part only).

Core: a Kite price socket that goes silent for 60 s is closed and reconnected with jittered backoff, every subscription is restored, and quotes stay stale until a fresh tick arrives.
Proof: replay a recorded Kite frame stream (tests/fixtures/kite_ws/) with a silent gap through KiteSocket with a fake clock and fixed random seed: the reconnect fires at 60 s, the waits are 1/2/4... s capped 30 s within +50% jitter, subscriptions are re-sent, and the QuoteBook shows 'stale' until the first fresh tick. Live window (owner Kite login): kill the network for 70 s and read the same sequence from the log.

Tier: A (live feed liveness; every quote's health state depends on it)

Spec basis:
REQ-114 AC-1: "Every 15 s each connection checks the time of its last frame of any kind"
REQ-114 AC-2: "After 60 s with no frame the connection is closed and reconnected"
REQ-114 AC-3: "Reconnect attempts wait 1 s, 2 s, 4 s and so on, doubling, capped at 30 s"
REQ-114 AC-4: "After reconnect every previous subscription is restored before the connection counts as healthy"
REQ-114 AC-6: "A refusal that means the session is gone"
REQ-114 AC-7: "Outside market hours (ADR-119 calendar) silence is expected"
REQ-133 AC-3: "A screen that has just connected or reconnected and has no tick yet"
ADR-165 (1): "Placing orders at Zerodha or any other broker is out of this scope"

Copy from: legacy-reuse.md rows 1, 3 and 8 (algochanakya ticker pool, kite adapter bridge, ticker/health.py), already adapted into backend/ofo_app/kite_ws.py and backend/ofo/marketdata/; extend those files, copy nothing new. Drop the TOTP categories (row 8).

Sensibull screens: no Sensibull equivalent in the study for feed internals (not visible from outside). The visible effect is a number that stops updating: Strategy Builder 010-039 and Option Chain header 060-067 (Fut Price, INDIAVIX); use the existing builder wording, add none.

Multi-broker review (read D:\Abhay\Ventures\competitors\multi-broker-architecture\2026-10-21\INDEX.md first): L5 (whose live prices: one platform-owned socket per user session, pattern A); no trap id applies directly; T6 (a gate that fails open) applies by analogy: a health check that errors must report stale, never healthy.

## What to build
1. backend/ofo_app/kite_ws.py (KiteSocket): add a per-connection last-frame clock (any frame incl. the 1-byte heartbeat; today only a data frame resets the backoff, kite_ws.py:170). A check task every 15 s (AC-1); at 60 s with no frame close and reconnect (AC-2). Silence is measured on the connection, never per contract (F-32).
2. Backoff: keep BACKOFF_START/BACKOFF_MAX (kite_ws.py:56-57), add random jitter of up to 50% of the wait, injected random source so a test fixes the seed (AC-3).
3. After reconnect, `_subscribe_all` (kite_ws.py:99) must complete before `provider.on_connected`-style healthy state; QuoteBook (backend/ofo/marketdata/feed_health.py:107) keeps every carried quote 'stale' until a fresh tick (AC-4). Test: reconnect, no tick yet, quote is stale, not available.
4. Session-gone answers (HTTP 403 today, kite_ws.py:102; also Kite TokenException and the 06:00 expiry via backend/ofo/broker/session.py expire_on_token_exception / expire_on_clock) stop reconnecting for that user and mark the session ended (AC-6). Never a retry loop.
5. Market closed (backend/ofo/market_calendar.py, ADR-119): silence is expected; health text 'market closed - last price <time>' and reconnect no more often than every 5 minutes (AC-7).
6. Log every disconnect, attempt and recovery with user, reason, timestamps and no token (AC-8) through backend/ofo_app/redaction.py.
7. Browser: backend/ofo_app/live_push.py + frontend/src/composables/useStrategyLive.js show 'Reconnecting - prices as of <time>' (REQ-114 AC-5) and 'Waiting for the first live price' with no live number until the first tick (REQ-133 AC-3); DATA_UNHEALTHY only after the REQ-049 window. Wording from the reviewed catalogue (ADR-003), not typed in the component.

## AC status (main plus open PRs, 2026-10-21)
| AC | Status | Where |
|---|---|---|
| 114 AC-1 | missing | no 15 s check in kite_ws.py |
| 114 AC-2 | missing | no silence timer |
| 114 AC-3 | partial | kite_ws.py:56-57,113-114 backoff 1..30 s, no jitter |
| 114 AC-4 | partial | kite_ws.py:99 re-subscribes; stale-until-fresh-tick unproven (feed_health.py:107) |
| 114 AC-5 | missing | frontend |
| 114 AC-6 | partial | kite_ws.py:102 handles 403 only |
| 114 AC-7 | missing | calendar exists (market_calendar.py), unused by the socket |
| 114 AC-8 | partial | provider hooks log; no reason/timestamps contract |
| 133 AC-3 | missing | live_push.py / useStrategyLive.js |
| evidence | none | evidence/ holds only README.md: no AC is verified yet |

## Every answer state of each outside system
Kite websocket: frame stream (stated) = normal. Heartbeat only (a 1-byte frame) = alive, counts as a frame. Silence 60 s = reconnect. HTTP 403 / TokenException / invalid token (failed, session gone) = stop, session ended, no retry. Network error / close (failed, transient) = backoff. Subscription cap reached (refused) = log and refuse, never drop silently. Empty subscription list (empty) = connect but no health alarm. Unknown close code (ambiguous) = treat as transient, log the code. Database: not touched by this item; if the session-ended write fails, the socket still stops and the failure is logged.

## Attack cases (reviewer: hands-on first)
- Fake clock jumps forward 61 s while ticks for ONE contract stop but heartbeats continue: no reconnect (quiet contract, F-32).
- Heartbeat stops but ticks continue (impossible on a healthy feed): the connection is alive.
- Jitter seed 0, 1, 2: every wait within [base, base*1.5] and never above 30 s*1.5; wait sequence never shrinks before the first data frame.
- Reconnect succeeds but `_subscribe_all` raises: the connection must not count as healthy.
- 403 on the third reconnect: loop stops, no further sleep scheduled.
- Saturday 12:00: no reconnect storm; at most one attempt per 5 min.
- Token appears in a log line or exception text: test fails.

Threat model: in scope: silent connection, jitter bounds, session-gone loops, stale-after-reconnect, token in logs; out of scope: a hostile Kite endpoint, forged frames (ADR-098), many-user load (REQ-050 AC-4 launch scope).

Findings checked: live-subscription-lost-on-release-reacquire, liveness-from-shared-subscribers, liveness-from-a-file-nobody-deletes, last-live-answer-kept-after-drop, staleness-by-last-change-age, wall-clock-assertion-flakes-under-load, state-read-after-await

Standing items: (a) applies: the 15 s check and the 5 min market-closed floor reuse one small timer budget; test that a slow health check never delays frame handling. (b) n/a: no CI step or import added. (c) n/a: no static detector added. (d) applies: every answer state of Kite listed above, each with a test.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Targeted tests: tests/marketdata/ (new test_reconnect_health.py), tests_app/test_kite_ws.py (find the existing file with Grep), tests_app/test_live_push*.py, frontend/tests for useStrategyLive; plus every file that names 'stale', 'disconnect' or 'reconnect' (grep tests/ tests_app/ frontend/tests first).
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (the one exception: a changed API model regenerates docs/api/openapi.json and is registered in tests_app/test_response_door.py, per builder-brief.md).
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Open
Open: technical: the market-closed reconnect floor (5 min) uses the ADR-119 calendar, which marks holidays but not the 09:15-15:30 window for a socket; proposal: treat outside 09:00-15:45 IST on trading days as closed for health purposes only, never as a gate on data. Live window needed for: AC-5 and AC-6 against real Kite (owner Kite login).
Open: business: none.
