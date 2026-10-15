# Verifier brief: W-065 phase 3 (frontend live screen + per-connection replay), Tier A, AC-4

Core: the Strategy Builder screen shows the server's pushed numbers over the platform WebSocket and, when the socket
drops, falls back to a REST refresh that is labelled not live - never old numbers presented as live.
Proof: the live push itself was proven on real Kite data on 2026-10-15 (57 pushes 13:47, 49 pushes 14:09). This round
judges the browser side and the replay: Playwright `frontend/e2e/strategy-live.spec.ts` at 1280 and 390 on the replay
API, and the unit/app tests, re-run by you.

Model: opus. Why Opus: Tier A verification (kit routing: Tier A verifier is Opus), adversarial judgement across a
frontend composable, a backend replay change and an e2e spec.
Budget: 45 min wall-clock, 32 tool calls (verifier maxTurns 40; batch commands). At budget stop and report what was verified and what was not.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), then the JSON block below.

## Where
- Worktree `D:\Abhay\Ventures\OptionsForOptions2-W-065v`, branch `build/W-065-frontend` (main merged in). Read-only:
  edit nothing, commit nothing, write no files except logs under `%TEMP%`.
- Diff to judge: `git diff origin/main...HEAD` (16 files: `frontend/src/composables/useStrategyLive.js`,
  `frontend/src/pages/StrategyBuilderPage.vue`, `backend/ofo_app/replay_mode.py`, `routes/live.py`, `routes/outcome.py`,
  `main.py`, `frontend/e2e/strategy-live.spec.ts`, `frontend/e2e/support/quiet-live.ts`, the tests).
- AC under test: REQ-035 AC-4, `ac_fp` faa18f01993e (check: `python tools/ac_fp.py REQ-035 AC-4`). W-065
  `tests_required`: `tests_app/test_strategy_live_push.py, frontend/e2e/strategy-live.spec.ts`.

## Spec basis
- REQ-035 AC-4: "Entry Price, LTP, Entry Value, Current Value, Unrealized P&L and P&L % update live"
- ADR-068 (2): "the screen falls back to a REST refresh when the socket is down, labelled as not live"
- ADR-068 consequence: "the screen does no P&L maths (ADR-008)"
- ADR-077: "When a strategy's live connection to the platform drops (the browser's own socket closes) and the screen
  falls back, it shows REQ-049 AC-5's message" and "No stale price outlives a subscription (unchanged); only its time is kept."
- REQ-049 AC-4: "Screens show when data is stale or unavailable instead of presenting old numbers as live."
- REQ-049 AC-5: "Live market data disconnected. Last updated: <time>. Live strategy monitoring is paused."

## Builder decision to judge (explicitly)
After a socket drop the screen shows AC-5's message with NO live numbers (rather than numbers from a REST call). Judge it against
ADR-077 and REQ-049 AC-4: is it spec-conformant, and do planned entries (ADR-068 (1), not live prices) still show?
Say conforms / does not conform, with the line.

## Checklist (each: how could it fail?)
1. No number is computed in the browser: grep the composable and page for arithmetic on money/P&L fields.
2. Pushes replace numbers only from the server message; numbers are never shown as live after `close`/`error`.
3. Drop -> AC-5 message with the newest price time (ADR-077), exact wording; never-priced strategy -> the draft
   label, not AC-5. ADR-020: "Draft — Live data not connected"
4. Reconnect: backoff bounded, no reconnect storm, socket closed on page unmount (no leak across navigation).
5. No token or credential on the socket URL or query string (legacy-reuse row 142 ADAPT: token off the query string).
6. `quiet-live.ts`: does holding the socket silent in the REST-path specs hide a real defect, or only make them
   deterministic? Name what each REST-path spec still proves.
7. Replay change (`replay_mode.py`): every connection gets its own replay; it stays TEST-ONLY (APP_ENV=test +
   OUTCOME_REPLAY=1) and can never run with LIVE_MARKET or against a real Kite URL.
8. Layout at 390 and 1280: no clipped numbers or message.

## Commands (run each yourself; this PC is fine for targeted runs; the database is ofo_test on a production host via
the tunnel on 127.0.0.1:5432 - targeted files only, never the full app suite)
- From the main checkout `D:\Abhay\Ventures\OptionsForOptions2`:
  `python scripts/orchestrator/db_run.py D:\Abhay\Ventures\OptionsForOptions2-W-065v python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_strategy_live_push.py`
- In the worktree's `frontend/`: `npx vitest run tests/strategy-live.test.js`.
- Playwright on the replay, as `.github/workflows/app-tests.yml` lines 237-271 do: start uvicorn with
  `APP_ENV=test OUTCOME_REPLAY=1` and `DATABASE_URL` from `db_run.py`'s environment on port 8001, `npm run build`, then
  `OFO_API_TARGET=http://127.0.0.1:8001 npx vite preview --port 4175 --strictPort`, then
  `npx playwright test e2e/strategy-live.spec.ts`. Logs to `%TEMP%`, tail only. Stop every server you start (kill by
  PID, never by a pattern that matches your own command line).

## Return
The evidence table, then exactly one JSON block:
```json
[{"ac": "AC-4", "requirement": "REQ-035", "ac_fp": "faa18f01993e", "result": "pass|fail",
  "commands": "<each command and its result line>", "observed": "<what you saw, incl. the builder-decision verdict>",
  "attack": "<what you tried to break and how it held or failed>"}]
```
Plus a list of defects (file:line, severity), if any.
