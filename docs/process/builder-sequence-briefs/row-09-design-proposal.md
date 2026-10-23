# Row 9 (REQ-113, price socket part) - orchestrator design proposal for independent review

Facts (Measure, 2026-10-22): the Kite price socket (`backend/ofo_app/kite_ws.py:63` KiteSocket) is owned by `LiveMarket`
(`live_market.py:75`), started in the API lifespan (`main.py:65-72`), closed on API shutdown (`main.py:78`). One socket for
one `OWNER_REF` (single user today; ADR-060 builds on the owner's Kite until the demo). 3000-instrument cap at
`kite_ws.py:55`, overflow truncated and counted (`kite_ws.py:175-177`), not refused+logged; per-key 3-connection cap only
in prose (F-57). No Redis in CI (`app-tests.yml:3` "Dropped: Redis service") or requirements. ADR-043 stack = Redis.
Owner rule: no system-level runtime (WSL, Docker, servers) installed on the laptop; tests that need Redis run in CI.
Order-update stream parts of AC-1/AC-4/AC-5 are deferred (order path, the table's deferred list).

Proposal (L row, always split):
- Part A backend (M/L): new entry `ofo_app/feed_main.py` (own process) owns LiveMarket and every user's socket; the API
  lifespan opens none (AC-1 test: API startup opens no websocket). Transport = Redis pub/sub (ADR-043; AC-3 "Once the
  market-data process and the API process both run, the internal bus (Redis per ADR-043) carries ticks"): channel per
  user, message carries the user ref (AC-5). Python `redis` client added to requirements-app.txt; local tests use the
  pure-python `fakeredis` package; CI app job gains a `redis:7` service and a real-Redis test. The bus holds no state
  that cannot be rebuilt; on bus loss every API consumer marks data stale (ADR-015) until a fresh tick. Token loaded in
  the feed process from the encrypted store; the egress gate installed in the feed process too (AC-7). Core test (AC-2):
  start a fake Kite websocket server replaying `tests/fixtures/kite_ws/frames-2026-10-08-092000-10s.bin.gz`, start the
  feed process and the API (subprocesses), kill and restart the API, assert the feed's connection count and last-message
  time show no reconnect.
- Part B backend (M): per-user sockets map (today one user, keyed by user ref), AC-9 kill-one-socket isolation, AC-8 06:00
  session end per user (close, publish "session ended", no reconnect), AC-6 caps as configuration with source+date
  (F-57), refuse and log beyond the cap.
- Part C frontend (S): AC-2 browser part - "reconnecting" state, resume within 10 s, never an old price as live.

Questions for the reviewer:
1. Is Redis pub/sub right for the first two-process version, or should part A use a simpler loopback transport? (AC-3
   text names Redis; deviating is a spec change.)
2. Is the split order right (A, B, C), and are the part sizes honest? Should B come before A?
3. Is the core test design (subprocesses + fake Kite server on recorded frames) sound and not flaky on Windows and on the
   CI Ubuntu runner? What would make it flaky?
4. What did I miss (dev workflow: who starts the feed process locally and in e2e/Playwright CI; the replay mode
   `OUTCOME_REPLAY=1`; the existing `tests_app/test_kite_ws.py`, `test_live_market_refuses_test_db.py`)?
