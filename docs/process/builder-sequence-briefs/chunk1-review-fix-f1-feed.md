# Chunk 1 Tier A review fix F1: the market-closed state on every price screen, and three feed MINORs

Common brief: docs/process/builder-brief.md (Budget hard stop: at 72 calls start nothing new, commit, report).
Size: M, about 12 files, 4 items, backend + frontend
CI: app tests job (`tests_app/` files you add or change; vars: DATABASE_URL via CI only - run NO database test locally); kit tests job (`tests/marketdata/`, `tests/` files you change); frontend job (`frontend/tests/` files you add or change).
Expected (orchestrator, before dispatch): 60 min / ~400k.

Core: on a closed market every quote's health reads market closed (never available), so the outcome, chain and index answers say so and every price screen shows the one market-closed banner.
Proof: step 1 is a failing test on the REAL path: a KiteProvider fed the recorded full frame, clock Saturday 2026-10-24 10:00 IST, one data frame then a heartbeat every second for 5 minutes. Today `feed.health` is AVAILABLE, the quote healths are ['available'] and the index answer state is LIVE (review attack, `review-a1/attack1.py` in the session-5 scratchpad). After the fix: market closed in all three, and the same run on Wednesday 2026-10-21 10:00 IST still reads available.
Class: market-state-decided-per-surface - every answer that carries a quote health (outcome, chain, index, live pushes) and every screen that shows a price: before, only the Settings card (live_market.feed_phase, routes/broker_status.py) reads the calendar; after, the one quote-health path does, and every price screen inherits it (structural guarantee, run-discipline C8; detector kept only as a second layer).

Spec basis: REQ-114 AC-7: "Outside market hours (ADR-119 calendar) silence is expected: the health check marks data market closed". ADR-177 (one market-closed wording). ADR-015 (no stale data shown as live). ADR-119 (the dated NSE calendar).
Copy from: none - this project's own feed-health path (`backend/ofo/marketdata/feed_health.py`) and calendar (`backend/ofo/market_calendar.py`).
Reference: screens catalogue 012, catalogue 200 - copy nothing new; RD-046/RD-068 are verified and their wording is the rule. RD-065 and RD-066 (REQ-114) are SPEC CHANGE records waiting for the owner (Q282), not built here.
Findings checked: verified-on-a-module-the-product-does-not-call, guard-as-forbidden-list.
That finding's 4th occurrence is this defect: your tests must exercise each SCREEN or ROUTE, not only the module.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-chunk1-copy`, branch `build/seq-chunk1-copy`, at the chunk head f7b7ab8f (frontend packages installed). Commit with `git commit -F <msg> -- <your paths>`, do NOT push. BINDING: never stop a process by name; stop only PIDs you started. Never call Kite live. Another Opus builder (F2) works at the same time in `-chunk1-copy-b2` on `backend/ofo/broker/`, `kite_http.py`, `routes/execute.py`, `strategy_store.py` and migration 0023: do not touch those files. If a commit is refused by `verifier_inflight_gate`, wait 2 minutes, retry once, keep editing. Scratch: `C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\5db71e90-61e3-4f1b-8a6c-a0ee38c54e11\scratchpad\f1`.

## What to do
1. MAJOR: put the calendar into the one quote-health path (`FeedState.health` / the QuoteBook read in `backend/ofo/marketdata/`), with the injected clock, so a closed market gives a not-live health (market closed) for every quote, whatever frames arrive. The outcome, chain and index answers carry `market_closed` and the last price time; the Strategy Builder, the Option Chain and the index strip mount the existing `MarketClosedBanner` with the ADR-177 text from `frontend/src/lib/sharedStateText.js` (one home). A calendar that cannot answer (a date past its data) reads closed (fail closed), as `is_market_open` already does. Keep `live_market.feed_phase` and `broker_status` on the same function, never a second copy.
2. MINOR: `backend/ofo_app/kite_ws.py:~319` resets the back-off on ANY data frame, so a link that sends one frame then drops reconnects every 0.5-1 s forever. Reset only after the connection has stayed up at least `CHECK_EVERY` (15 s) with data.
3. MINOR: `backend/ofo/marketdata/reconnect_policy.py:~43` - the closed-hours 300 s wait is not capped by the next open: a drop at 09:14:59 leaves 09:15-09:20 with no feed. Wait min(300 s, seconds until `market_calendar.next_open(now)`) when known.
4. MINOR: "Reconnecting - prices as of <time>" uses the push's server time (`answered_at`), not the last price time. Send the snapshot's last-price instant in each push and show that.

Attack list: (each names its test file)
1. Saturday 10:00 IST with heartbeats: quote health, outcome answer, chain answer and index answer all market closed; the three screens show the banner text (a new `tests/marketdata/` test + a `tests_app/` route test, DB-free, + `frontend/tests/` per screen).
2. Wednesday 10:00 IST same frames: available; holiday 2026-10-20 10:00: closed; a 2027 date past the calendar: closed.
3. One frame then drop, repeated: waits grow, never below 1 s after the third flap (a `tests_app/test_kite_ws*.py` test with a fake clock).
4. Drop at 09:14:59 on a trading day: next connect at or before 09:15:00 + spread.
5. Push after quotes turn stale: the shown time equals the last price time, not the push time (frontend test).

Standing items: (a) the reconnect wait change is a time-driven rule: a test shows the market-hours back-off (1, 2, 4 ... 30 s) is unchanged; (b) n/a: no CI step changes; (c) n/a: no static detector added (the structural path is the guarantee); (d) the calendar's answer states - open, closed (weekend, holiday, after hours, pre-open), unknown date (past its data) - each with what the health and each screen show.
Threat model: in scope - a closed market shown as live on any price screen, a reconnect storm from a flapping link, a lost first minutes of the session; out of scope - the calendar's data itself (ADR-119), order placement.
Mutation gate: run `python scripts/orchestrator/mutation_gate.py` on: the calendar check removed from the health path; the back-off reset back on any frame; the next-open cap removed; for frontend mutants run each by hand on a copy of `frontend/` in your scratch folder and record killed/survived.
Reviewer checklist: one market-state function, every price screen inherits it; the ADR-177 text from its one home; fail closed on an unknown date; no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (except docs/api/openapi.json if a response model changes - regenerate with `python scripts/generate_openapi.py`).

Tests: python -m pytest -q -p no:cacheprovider tests/marketdata; python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests; python -m pytest -q -p no:cacheprovider -c pytest-app.ini <your DB-free tests_app files>; in frontend/: npm run lint, npx vitest run <your files> (ONE full `npx vitest run` at the end; learn.test.js `\r` is local-only)
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table
