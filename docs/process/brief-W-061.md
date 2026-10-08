# Builder brief: W-061 Save Draft - strategy store in PostgreSQL

Core: a real NIFTY 13-Oct-2026 Iron Condor built from catalogue contracts saves through Save Draft and loads back
exactly equal through a new database connection.
Proof (step 1, CI on PostgreSQL as ofo_app): the work item's `proof` steps as `tests_app/test_strategy_store.py`,
written first and red, before the store exists.

Why Opus: Tier A - a new migration, an API that writes user data, and the definition/live-state boundary.
Budget: 60 min wall-clock, 80 tool calls. Commit domain serialisation first, then the store, then the API; at budget
stop after a commit and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`).
Tier: A.

## Spec basis
- REQ-038 AC-5: "A strategy's definition and its activity history are saved in the database when the user presses Save Draft,
    survive a restart, and load back exactly as saved; live prices are never saved inside the strategy."
- REQ-038 AC-1: "Definition (underlying, expiry, legs, strikes, side, quantities, rules, risk limits, preferences) and live
    state (spot, futures, LTP, bid/ask, volume, OI, OI change, IV, Greeks, P&L, margin, charges, distances, trigger
    state, timestamps, data health) are separate objects."
- REQ-038 AC-2: "Before the first execution, definition changes are kept as simple activity-history entries with restore, not
    versions"
- Copy from: legacy-reuse rows `app/models/strategies.py` (REFERENCE) and `app/api/routes/strategy.py`,
  `app/schemas/strategies.py` (REFERENCE/SKIP: float P&L and optional strategy_id are not copied).

## Start
- Branch `build/W-061-save-draft` from `origin/build/W-058-kite-login` (migration 0006 is there), then
  `git merge origin/main` (main carries REQ-038 AC-5, work/W-061.md and this brief); resolve any conflict keeping both
  sides' lines in docs/process/coverage-stages.yaml.
- Read `backend/ofo/strategy/definition.py`, `versions.py`, `builder_history.py`, the W-057 catalogue store
  (`backend/ofo_app/catalogue_store.py`) and `backend/ofo_app/alembic/versions/0006_broker_sessions.py` first.

## What to build
1. **Domain serialisation (backend/ofo/strategy/, stdlib):** a canonical, versioned JSON form of `StrategyDefinition`
   and of an activity-history entry; legs reference the catalogue's internal contract id (W-057), never Kite's token
   or symbol; every number is a Decimal written as a string. Round trip is exact (test with the real Iron Condor and
   with rules, limits and preferences filled). Unknown keys or a missing contract id are refused on load.
2. **Migration `0007_strategy_store`** (down_revision 0006), through the existing allowlist chain helper:
   `strategies` (id, user_ref, underlying, status CHECK in ('draft'), created_at/updated_at by the database clock,
   definition JSONB, definition_schema_version) and `strategy_history` (append-only: strategy id, seq, at, change
   summary, definition JSONB); app role SELECT/INSERT, UPDATE only of `definition`/`updated_at` on strategies, no
   DELETE, no UPDATE on history (guard trigger + grants, as W-057 did). Column-name allowlist: no ltp, bid, ask,
   volume, oi, iv, delta, gamma, theta, vega, pnl, margin, spot or price column may exist (a test reads the
   catalogue of the database and asserts it).
3. **Store** `backend/ofo_app/strategy_store.py`: save_draft (new strategy), update (writes a history entry of the
   previous definition, then the new one, in one transaction), load, list, restore(history seq) (itself a new history
   entry - restore never deletes history).
4. **API** (FastAPI, user "owner" as in W-058): `POST /strategies` (Save Draft), `GET /strategies`,
   `GET /strategies/{id}`, `PUT /strategies/{id}`, `GET /strategies/{id}/history`, `POST /strategies/{id}/restore/{seq}`.
   Bodies carry definitions only; a body field from the live-state list is refused (422), never dropped silently.
   Commit the OpenAPI slice (`scripts/generate_openapi.py`).

## Standing items (run-discipline B4) and reviewer checklist
- Mutation tests first: store a float instead of a Decimal string; allow a live-state column; allow DELETE on
  history; update without a history entry; restore that deletes later entries. Each must turn a test red.
- (d) every answer state of a load: found, not found, another user's id, schema version unknown, contract id no
  longer in the catalogue (refuse with a fixed code, never guess a replacement - ADR-016), JSON malformed.
- Fail closed: any error inside update stores nothing (one transaction).
- Expected values from the real fixture and the spec, never from running the code.
- Kit CI stays green: tests/ imports no app packages; no wall-clock asserts.

## Rules
- Do not edit kit files or spec/. Never write `evidence/`. Never mark anything verified or reviewed.
- Domain suite + `python -m pytest -c pytest-app.ini -q` once at the end (DB tests skip locally; say so); output to
  a log file, tail only. Commit and push `build/W-061-save-draft`.
