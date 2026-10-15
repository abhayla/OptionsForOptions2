# Builder brief: W-065 phase 1 - live market data in the app and the strategy push (server side + proof script)

Core: the running app holds a live `KiteProvider` fed by `KiteSocket` with the owner's stored W-058 session, and a
platform WebSocket pushes recomputed outcome numbers for one strategy at most once a second, only when an input
changed. Today `routes/outcome.py:get_market_context()` returns None outside the test replay mode.
Proof: phase 1 ends with `docs/research/kite-proof-2026-10-07/w065_live_push_proof.py` ready; the orchestrator runs it
live after 09:15 IST with the owner's login (work/W-065.md `proof`). Build the thinnest path that makes that run
possible FIRST (live context + push endpoint + proof script), then the tests and states around it.

Tier: A. Model: sonnet/medium (kit routing: builder, always).
Budget: 60 min wall-clock, 75 tool calls. Commit after each numbered step; at budget stop after a commit and report
done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words.
Copy from: legacy-reuse rows 57 (`app/websocket/manager.py`, REFERENCE: connection-manager pattern only) - the server
side builds on W-059 (`ofo.marketdata.fanout.FanOut`, `kite_provider.KiteProvider`, `ofo_app.kite_ws.KiteSocket`),
not on algochanakya's ticker. Row 142 (`useWebSocket.js`) is phase 2 (frontend), not now.

## Spec basis
- ADR-068 decision: "The server pushes recomputed strategy numbers to the browser over the platform
  WebSocket at most once a second per strategy, and only when an input changed"
- REQ-035 AC-4: "Entry Price, LTP, Entry Value, Current Value, Unrealized P&L and P&L % update live"
- REQ-048 AC-1: "Data flows Vendor → Market Data Gateway → Normalization → fast cache → internal event stream → Option Chain"
- REQ-048 AC-4: "Provider streams are shared and fanned out internally; there is no vendor subscription per user"
- ADR-008: one engine; the push carries `ofo.outcome.build_outcome` results serialized exactly as the REST outcome
  route does (`outcome_to_dict`, money as strings); nothing is computed in the browser.

## Start
- Worktree `C:\Abhay\Ventures\OptionsForOptions2-W-065`, branch `build/W-065-live-push` from main a2d8513. The
  orchestrator already put `work/W-065.md` and this brief there: commit both first.
- Read: `backend/ofo_app/main.py` (lifespan, replay wiring), `config.py`, `routes/outcome.py` (MarketContext,
  get_market_context, strategy_outcome), `replay_mode.py` (how a KiteProvider is built from the catalogue rows),
  `kite_ws.py`, `broker_token_store.py` (`access_token_for`), `broker_config.py`, `catalogue_store.py`,
  `backend/ofo/marketdata/fanout.py`, `kite_provider.py`, `backend/ofo/outcome/`.

## What to build
1. **Live market context** (`backend/ofo_app/live_market.py`): a setting `LIVE_MARKET` (default off; tests never turn it
   on against Kite). When on, the lifespan reads the owner's active session (`access_token_for`, user "owner" as in
   W-058), builds a `KiteProvider` over the catalogue rows of NIFTY/SENSEX index + the live NFO/BFO contracts it
   needs, starts `KiteSocket.run()` as a background task, and stops it on shutdown. `get_market_context()` returns the
   live context; with no active session it stays None ("Draft - Live data not connected", unchanged). Session ended
   (403) -> context goes not-live, logged without the token. The REST outcome route then works live too.
2. **Push endpoint** `WS /api/strategies/live`: the client sends one OutcomeRequest JSON (same model as REST); the
   server subscribes the legs' instruments (and the underlying index) through the shared stream, then loops: at most
   once a second, and only if a quote of an input instrument changed since the last push, it computes the outcome with
   the same function as the REST route and sends it. A client message replaces the strategy. On close: unsubscribe.
   Bad input -> one fixed error message through the catalogue (W-024 rules: no free text, no exemption added); if a
   W-024 guard test refuses the shape, STOP and report rather than adding an exemption.
3. **Proof script** `docs/research/kite-proof-2026-10-07/w065_live_push_proof.py` (stdlib + `websockets`): takes the
   API base URL; reads the live NIFTY spot via the REST outcome or a health route; builds a NIFTY iron condor on the
   nearest live expiry (sell CE/PE ~ +-200 from spot rounded to 50, buy wings +-400; lots 1) from the catalogue; opens
   the push; records 60 s; prints counts only: pushes, min gap (s), distinct LTP values per leg, distinct Unrealized P&L
   values, data-health states seen; exits 0 only if pushes >= 30, min gap >= 1.0, LTP and P&L changed, health live.
   Writes the summary JSON (no token, no personal data) next to itself.
4. **Tests** (`tests_app/test_strategy_live_push.py`, on the W-064 replay provider and a fake clock): one push per
   second at most when ticks arrive faster; no push when no input changed; the push equals the REST outcome for the
   same snapshot; a new client message replaces the strategy; unsubscribe on close (fan-out subscriber count back to
   0); no session -> not-connected state; session ended -> not-live; `LIVE_MARKET` off by default and never on under
   `APP_ENV=test` with a real Kite URL.

## Reviewer checklist (write these first; each must turn a test red when mutated)
- Mutation: push on every tick (no 1 s gate); push when nothing changed; skip unsubscribe on close; compute any number
  outside `build_outcome`; let the token reach a log line or the proof output.
- Tier A: the access token is never logged, printed, sent to the browser or written to disk by this item.

## Rules (this PC is the Windows VPS that also serves IPODhan production's database - owner decision 2026-10-09)
- Targeted test files only; NEVER the full app suite, Playwright, npm or `tools/ci_local.py`. DB-backed tests via
  `python scripts/orchestrator/db_run.py C:\Abhay\Ventures\OptionsForOptions2-W-065 python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_strategy_live_push.py`
  run from `C:\Abhay\Ventures\OptionsForOptions2`. ofo_test is at W-061's 0008: do NOT run alembic in this item (no
  migration here). Domain: `python -m pytest -q -p no:cacheprovider tests/marketdata tests/outcome`.
- Do NOT connect to Kite or run the proof script; the orchestrator runs it live with the owner. Start no servers you
  do not stop; logs to `%TEMP%`, tail only. Each gate its own command; commit/push separately.
- Do not edit kit files or `spec/`. Never write `evidence/`. Never mark anything verified/reviewed.
- Commit and push `build/W-065-live-push`. Do not open a PR.
