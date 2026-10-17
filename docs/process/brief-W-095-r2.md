# Builder brief: W-095 round 2 - finish the Execute route on the merged pieces (Tier A: order path, money)

Core: `tests_app/test_execute_route.py::test_core_real_order_entry_then_exit` passes on the real data: strategy id 1
(inserted with that EXPLICIT id, so the tags are the real OFS1V1L0 / OFS1V2L0), ENTRY -> one order equal to the real
basket `tests/fixtures/kite_replies/basket-121848.json` except the price = 3.35 from the real 15:07:20 depth (BUY 65),
plan 1 stored open; `close_plan(..., reason="filled", filled={"OFS1V1L0": 65})`; EXIT -> SELL 65 LIMIT 3.30 tagged
OFS1V2L0, plan 2 stored open.
Proof: that DB test, red now (round 1 never ran it), green after - run ONCE locally through `db_run.py` (see Rules).

Round 1 (branch `build/W-095-execute-route`, head 0ebf51d) stopped at budget with the core unproven. Since then
W-093 (`kite_reads.py`), W-097 (`live_market.latest_depth`) and W-098 (sealed proofs) are on main, and W-094 (the plan
store + migration 0016) is final on `origin/land/W-094` (Tier A review running; its API will not change).

Tier: A. Model: opus.
Why Opus: finishing a multi-file Tier A integration whose first round guessed an API and departed from REQ-060 AC-7.
Budget: 80 min wall-clock, 76 tool calls. HARD limit: at call 72 commit, push, report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words, plus each guard and its
killing test (mutation-run, not by design), plus the final `alembic current` line read from the MAIN checkout.
Copy from: legacy-reuse map row 101 (`app/api/routes/orders.py`) reference only - nothing copied (ADR-008 / ADR-002).
Findings checked: caller-supplied-verdict-trusted, state-read-after-await, margin-gate-blocks-closing-basket,
trust-broker-status-word, store-rule-enforced-per-call-site, repo-wide-scan-outside-targeted-tests,
branch-migration-tests-move-shared-db, design-misses-cross-cutting-safeguard
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py

Read first: `docs/process/brief-W-095.md` (round 1's brief: all its rules still apply), `docs/process/builder-brief.md`,
`spec/decisions/ADR-105.md` (on the docs branch: read `docs/process/gc-2c-design-review-2026-10-17.md` decisions instead
if ADR-105 is not on main yet), `backend/ofo_app/execution_plan_store.py` from `origin/land/W-094`.

## Spec basis
- REQ-073 AC-1: "Execute Strategy turns the execution plan (REQ-056) into one Kite basket of LIMIT orders marked read-only, in
    the plan's order; the user cannot change a price, quantity or contract on Kite's page."
- REQ-060 AC-7: "A broker position in no strategy and not recorded as standalone is offered the grouping choice (Q24)
    and blocks no strategy. A mismatch blocks only the strategy whose contract quantity disagrees (Q199)."
- ADR-050 item 4: "(b) persist the order intent before sending"

## What round 2 must do (each is a defect in round 1)
1. Start: `git fetch origin && git checkout -B build/W-095-execute-route origin/build/W-095-execute-route`, then
   `git merge origin/main` and `git merge origin/land/W-094`; after each merge run `python scripts/ruff_ratchet.py`.
2. The REAL store API (round 1 guessed it): `PlanOrder(leg_index, tag, instrument_id, tradingsymbol, transaction_type,
   quantity, price, filled_quantity=None)`, `StoredPlan(..., close_reason)`, `PlanStoreError.code`,
   `next_plan_number(conn, user_ref, strategy_id, *, floor=0)`, `record_plan(conn, user_ref, strategy_id, plan_number,
   action, orders)`, `plans_for`, `open_plan`, `close_plan(..., reason, filled=None)`. Never edit the store.
3. Production depth = `ofo_app.live_market.latest_depth(instrument_id)` (W-097; returns the domain `Depth` or None).
   The quote-reader seam stays for tests (the real 15:07:20 fixture). No depth -> refuse that leg.
4. Reconciliation (REQ-060 AC-7, design review finding 6): round 1 made unexplained broker units block the strategy -
   that contradicts AC-7. Platform side = DB-derived filled quantities of this strategy's plans (entry +, exit -);
   broker side = Zerodha net. The strategy is blocked when Zerodha holds FEWER units than the strategy on a contract,
   or the opposite side; units BEYOND the strategy's block nothing. Use `ofo.reconciliation.compare.compare` /
   `blocking.blocked_strategy_ids` if they can take request-built inputs (a `StrategyRecord` built inside the request
   from stored data and thrown away is allowed); if they cannot, write ONE function with AC-7's three cases tested
   (surplus -> not blocked; shortfall -> blocked; side flip -> blocked) and say why compare could not be used.
5. Response: the browser must POST exactly `KiteBasket.form_fields(api_key)` to `KITE_BASKET_URL`; a client that
   rebuilds the JSON could drop `readonly` or a tag. Return the exact `data` string in a NARROW closed type (e.g. a
   pydantic type that only accepts a string which parses back to the basket's own orders, readonly true, tags of this
   plan) plus `api_key` and `basket_url`; the structured `orders` may stay for display. Say which type you used.
6. `pro_entitled` from the entitlement store (`ofo_app.entitlement_store.load`) - never None when a source exists.
7. Ruff ratchet: round 1 rose 7 rules (C901, E501, I001, PLR0912, PLR0913, PLR0915, PLW0108) - split `routes/execute.py`
   into small functions until `ruff_ratchet.py` says no rule rose.
8. Tests round 1 left out: two concurrent EXITs for strategy 1 -> one basket, the other refused (`plan_open`); a
   standalone surplus does not block; a shortfall blocks; and one mutation run per guard (name the killing test).

## Rules
- DB: the shared test DB must END at main's head `0015_audit_broker_allowlist`. Run DB commands through the MAIN
  checkout's helper with your worktree as cwd: `python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run.py <your worktree> python -m alembic -c backend/ofo_app/alembic.ini upgrade head`,
  then ONLY `tests_app/test_execute_route.py`, then `... downgrade 0015_audit_broker_allowlist`, then
  `python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run.py D:/Abhay/Ventures/OptionsForOptions2 python -m alembic -c backend/ofo_app/alembic.ini current`
  -> paste it. Never copy `.env` into a worktree. Never run `atool.py` without `--no-tests`, and never its route-test
  step (it replays migrations against the shared DB - finding branch-migration-tests-move-shared-db, 2 occurrences).
- Before every push: `python -m pytest -q -p no:cacheprovider tests/errors/ tests/test_*.py` (10-40 s, no DB) and
  `python scripts/ruff_ratchet.py`.
- Add `W-095: 4b` under `work_items:` in `docs/process/coverage-stages.yaml` (after W-094).
- No UI, no return route (W-096), no store edit. No kit or `spec/` edit, no `views/`, no findings INDEX, no regenerated
  files, no `evidence/`. Commit and push `build/W-095-execute-route`. No PR.
