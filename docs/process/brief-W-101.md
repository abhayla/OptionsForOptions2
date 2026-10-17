# Builder brief: W-101 Test-only Execute/return replay - the recorded Kite session behind both order routes (Tier A: test code inside the order path, a guard on APP_ENV)

Core: with `APP_ENV=test` and a new switch `EXECUTE_REPLAY=1`, the running API answers `POST /strategies/1/execute`
`{"action": "ENTRY"}` with BUY 65 NIFTY26O1923650CE LIMIT 3.35 (tag OFS1V1L0) from the recorded 2026-10-16 Kite
replies (no live Kite session, no live feed), and the return route on the 122104 replies closes plan 1 filled with
0 mismatches. Any other `APP_ENV` refuses the switch at start-up, before anything is served.
Proof: a CI job step in `.github/workflows/app-tests.yml` (project-owned file; edit it with the Edit tool) starts the
replay API with `EXECUTE_REPLAY=1`, seeds strategy 1 + a Pro grant, and runs the two calls over HTTP, asserting the
exact values above. The route tests' own core sequence (`test_core_real_order_entry_then_exit`) is the model.

Tier: A. Model: opus.
Budget: 70 min wall-clock, 72 tool calls. HARD limit: at call 68 commit, push, report.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 300 words, `git status --short` empty,
each new guard with its killing test (mutation-run).
Copy from: none - test seams already exist in `tests_app/test_execute_route.py` (`_session_for`, `_Quotes`, `AT`) and
`tests_app/test_execution_return.py`; move what you need into the backend module instead of re-writing it, and keep the
tests importing it from there (no second copy).
Findings checked: caller-supplied-verdict-trusted, live-work-shares-test-database, setting-read-from-two-sources, store-filled-only-by-tests, repo-wide-scan-outside-targeted-tests, request-clock-for-database-stamped-fact
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py

## Spec basis
- REQ-073 AC-4: "No code path places an order through the order-placement API; a test fails if one is added."
- REQ-073 AC-3: "When the user returns from Kite, the platform reads the actual order states and positions from Zerodha and
  reconciles them"
- The outcome replay pattern (`backend/ofo_app/replay_mode.py`, W-064): "Any other ``APP_ENV`` refuses the setting at
  start-up" - same rule here.

## Build
1. New module `backend/ofo_app/execute_replay.py` (TEST-ONLY): `replay_requested()` reads `EXECUTE_REPLAY`;
   `require_test_env(app_env)` raises unless `app_env == "test"`; `create_app` (main.py) calls it before any router is
   added, next to the outcome replay block, and overrides `execute.get_kite_session`, `execute.get_quote_reader`,
   `execute.get_execute_clock` and the return route's session/clock dependencies (read
   `backend/ofo_app/routes/execution_return.py` for their names) with the recorded replies:
   - Execute: the same replies `test_core_real_order_entry_then_exit` uses for its ENTRY step (orders/positions before
     the order, funds, `margins-basket-entry-derived.json`, `quote-150720.json` for the band), depth from
     `tests/fixtures/kite_ws/full-frame-12080386-150720.bin`, the test's market-hours instant `AT` as the pinned clock.
   - Return: `orders-122104.json`, `trades-122104.json`, `positions-122104.json`.
   - The api_key the basket carries is a fixed test value (never read from `.env`).
   Nothing in it opens a socket or calls Kite; the transport is the recorded files only (REQ-073 AC-4's runtime egress
   gate stays installed - do not bypass it).
2. A seed command `python -m ofo_app.seed_execute_replay` (refused outside `APP_ENV=test`, same guard) that stores
   strategy id 1 exactly as the route test stores it, and a Pro grant through `entitlement_store.append` (database
   clock - never a request-clock value; finding request-clock-for-database-stamped-fact). Idempotent on re-run.
3. `app-tests.yml`: a step that starts a second replay API (its own port, `EXECUTE_REPLAY=1`), runs the seed, then a
   pytest file `tests_app/test_execute_replay_api.py` marked so the normal app suite skips it unless that server's URL
   is set, which POSTs Execute ENTRY and then the return call and asserts: orders == [BUY 65 NIFTY26O1923650CE LIMIT
   "3.35" tag OFS1V1L0]; return -> plan 1 `filled`, mismatches 0. Stop the server at the end of the step.
4. Unit tests (no DB): switch off -> no override installed; switch on with `APP_ENV` in {"", "production",
   "development", "staging"} -> start-up refused (generated list, not hand-picked); switch on + test -> overrides
   installed; the seed command refuses outside test.

## Reviewer checklist (the Tier A reviewer checks exactly this; attack cases first)
- Attack: start the app with `EXECUTE_REPLAY=1` and `APP_ENV=production` -> must raise before any route is served.
- Attack: `APP_ENV=test` without the switch -> the real `get_kite_session` is used (no override leaks).
- Attack: does any path in the replay module import an HTTP client or open a socket? (grep + the egress gate).
- The seed's grant time comes from the database clock (read the SQL).
- No second copy of the test seams: the route tests import the moved helpers.
- The CI step asserts the exact strings above, and the server is stopped.

## DB
NOT the shared-DB holder (W-103 holds ofo_test this run). Run NO DB command locally; the DB tests and the replay API
step run in CI on its own PostgreSQL. Your local runs: the unit tests above + the Tests line + `python
scripts/ruff_ratchet.py` + `python -m pytest -q -p no:cacheprovider -m "not network" tests` once (domain, no DB).

## Rules
- Branch `build/W-101-execute-replay` from origin/main. Work card `work/W-101.md` (frontmatter shape of
  `work/W-100.md`; requirement_ids [REQ-073]; tier A; depends_on [W-095, W-096]; tests_required
  ['AC-4: tests_app/test_execute_replay.py', 'AC-3: tests_app/test_execute_replay_api.py']) and `W-101: 4b` in
  `docs/process/coverage-stages.yaml`.
- Never copy .env; no PR. No kit or `spec/` edit, no `views/`, no `evidence/`. Common rules: `docs/process/builder-brief.md`.
