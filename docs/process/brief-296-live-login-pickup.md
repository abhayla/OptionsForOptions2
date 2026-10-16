# Builder brief: #296 live market picks up a Kite login made after the API started (Tier A: live-data liveness)

Core: with `LIVE_MARKET=1`, an API started while no Kite session is stored answers `NOT_CONNECTED`; after a successful
`GET /kite/callback` stores a session, the next outcome call answers `COMPUTED` with no process restart.
Proof (unit, then LIVE today before 15:15 by the orchestrator): an app test with a fake socket: start with no session ->
state `not_connected`; run the callback's store path -> `LiveMarket` restarts and `context()` is not None. Live: the
orchestrator restarts the API with no session, the owner logs in in a private window, outcome goes COMPUTED.

Model: opus. Why Opus: live-data liveness across the lifespan, the login route and a background task; a wrong restart
can leak a second socket or a token.
Budget: 45 min wall-clock, 90 tool calls. At budget STOP and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 300 words.
Copy from: none - this repo's `backend/ofo_app/live_market.py` / `main.py` / `routes/broker.py` (W-058, W-065);
algochanakya's ticker restart is not in the legacy-reuse map.

## Class (defect-fix contract)
- RCA: `LiveMarket.start` reads the stored session once in the app lifespan (`main.py` `_lifespan`); nothing re-reads
  it when `kite_callback` stores a new session, so state stays `not_connected` (or `session_ended`) until a restart.
- Class: every login completed while the app runs with LIVE_MARKET on and the market state is `not_connected` or
  `session_ended` (incl. the daily login after the token stops ~04:30 IST, F-37). Before: 100% need a restart; after: 0.
- Failing test first on the real `LiveMarket` + callback path.
- Detection: a test asserting state transitions not_connected -> live and session_ended -> live after a stored login.

## What to build (shape is yours; these are the constraints)
- After `kite_callback` stores a session successfully, (re)start the live market if `live_requested()` and the state is
  not `live`. Old socket/task stopped and awaited first: never two sockets (assert one task named `kite-socket`).
- A login while state is `live` does nothing to the running socket (no double subscribe).
- The token never logged, printed, put in an exception message or a task name (existing rule in `live_market.py`).
- Restart failure leaves state `not_connected` and the login still succeeds (log class name only).
- Concurrency: two callbacks at once start one market (a lock).
- Optional, only if cheap: a 60 s retry while `not_connected` - skip it if the callback path covers the class.

## Reviewer checklist (Tier A reviewer attacks these - test each first)
1. Two concurrent callbacks -> one socket task. 2. Callback while live -> no restart. 3. session_ended -> live after
login. 4. Restart raising -> login response unchanged, state not_connected. 5. No token in logs (caplog assert).
6. App shutdown after a restart stops the new task (no pending-task warning). 7. LIVE_MARKET off -> callback never
starts a market. 8. APP_ENV=test with real Kite URL still refused.
Findings classes checked: grep `knowledge/findings/` for `live`, `session`, `restart` before designing.

## Rules
- Your own worktree, branch `fix/296-live-login-pickup` from `origin/main`.
- Targeted tests: the app test files for live_market and broker routes, via
  `python scripts/orchestrator/db_run.py . python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/<file>.py`
  only if they need the DB; `python scripts/ruff_ratchet.py`.
- No new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; no regenerated files in the PR.
- Commit and push; do not open the PR; never write `evidence/`, `work/` or the spec.
