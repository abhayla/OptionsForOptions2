# Builder brief: W-095 Execute route - saved strategy -> gate -> read-only Kite basket, intent persisted first (Tier A: order path, money)

Core: `POST /api/strategies/1/execute {"action": "ENTRY"}` on strategy id 1 (BUY 65 NIFTY26O1923650CE, the owner's
real 2026-10-16 order) returns a basket whose one order equals the recorded real basket
(`D:/Abhay/Ventures/ofo-kite-ticks/2026-10-16/real-order/basket-121848.json`: NFO, NIFTY26O1923650CE, BUY, LIMIT,
NRML, quantity 65, readonly true, tag OFS1V1L0) except the price, which is ADR-080's executable limit from the REAL
depth quote of 15:07:20 (`real-order/fetch.json` key `quote`: asks 3.35/56810 -> BUY 65 LIMIT 3.35); plan 1 is stored
open. After plan 1 is closed as `filled` (through the W-094 store, standing in for the return route), `{"action":
"EXIT"}` returns SELL 65 LIMIT 3.30 (best bid 3.30) tagged OFS1V2L0 - the real exit's tag.
Proof: step 1 is `tests_app/test_execute_route.py::test_core_real_order_entry_then_exit` (a DB test; CI proves it,
locally only this file through `db_run.py`). Write it FIRST, red. Copy the quote and the basket rows into
`tests/fixtures/kite_replies/` as `quote-151720.json` and `basket-121848.json` (redact nothing else; they carry no
client id - assert it as the README's test does) and add them to that folder's README table and its file-count test.

Tier: A (order path, money, the pre-execution gate). Model: opus.
Why Opus: multi-file integration across the domain gate, margin, eligibility, freeze, basket and two parallel items.
Budget: 90 min wall-clock, 80 tool calls. HARD limit: at call 76 commit, push, report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words, plus a table of every
`ExecutionContext` field -> the source you filled it from.
Copy from: legacy-reuse map row 101 (`app/api/routes/orders.py`) reference only - its float money and optional
strategy_id break ADR-008 / ADR-002; nothing copied.
Findings checked: caller-supplied-verdict-trusted, state-read-after-await, margin-gate-blocks-closing-basket,
trust-broker-status-word, money-parsed-through-float, store-rule-enforced-per-call-site, fixture-symbol-not-in-catalogue,
targeted-tests-miss-dependent-files, guard-as-forbidden-list
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py

Read first: `docs/process/builder-brief.md` (every line applies; B4 standing items: list every answer state of each
outside system and what it does), `CLAUDE.md`, `backend/ofo/execution/context.py` (whole docstring), `safety.py`
(`check_pre_execution`), `basket.py`, `backend/ofo_app/checked_basket.py`, `eligibility_from_zerodha.py`
(`fresh_registry`), `freeze_store.py` (`review_freeze_limits`) with `ofo/execution/freeze.py` (`freeze_check`),
`catalogue_store.py` (`load_catalogue`), `live_market.py` (`owner_margin_client`), `strategy_store.py`,
`routes/strategies.py` (route, error boundary and `ApiModel` style), `ofo/engine/executable_price.py`
(`depth_from_quote`, `executable_limit`), `ofo/execution/price_check.py` (`circuit_block`), `tests_app/test_checked_basket.py`.

## Spec basis
- REQ-073 AC-1: "Execute Strategy turns the execution plan (REQ-056) into one Kite basket of LIMIT orders marked read-only, in
    the plan's order; the user cannot change a price, quantity or contract on Kite's page."
- REQ-073 AC-4: "No code path places an order through the order-placement API; a test fails if one is added."
- ADR-050 item 4: "(b) persist the order intent before sending"
- ADR-080: "Execute at current market conditions" sets each leg's LIMIT from depth: "(3) Q268: "Execute at current market conditions" sets each leg's LIMIT to the worst price level in Kite's 5-level
  depth needed to fill the whole quantity (BUY: ask side, SELL: bid side), rounded per (2)"
- REQ-055 AC-3: "The platform's own margin figure is shown as a planning estimate; Zerodha's figure is authoritative."
- Technical decisions (orchestrator, GC-2c design review 2026-10-17; decision row in the GC-2c docs batch): the tag's
  plan version is a per-strategy plan number (entry 1, exit 2 on the real order), never the domain Version number;
  one open plan per strategy; the EXIT's active legs are the orders of the latest ENTRY plan closed as `filled`
  (persisted, so a restart never loses them); this route does not touch the in-memory `StrategyRecord`.

## Parallel items you integrate (both on origin, pushed as they finish)
- W-093 `backend/ofo_app/kite_reads.py`: `KiteReads(*, api_key, access_token, transport)` with `fetch_orders() ->
  list`, `fetch_trades() -> list`, `fetch_positions() -> Mapping`, errors `KiteReadError(code)`. Branch
  `build/W-093-kite-reads`.
- W-094 `backend/ofo_app/execution_plan_store.py`: `PlanOrder`, `StoredPlan`, `PlanStoreError(code)` (`plan_open`,
  `not_found`, `bad_plan`, `tag_taken`), `next_plan_number(conn, user_ref, strategy_id, *, floor=0)`,
  `record_plan(conn, user_ref, strategy_id, plan_number, action, orders)`, `plans_for`, `open_plan`,
  `close_plan(..., reason)`; migration `0016_execution_plans`. Branch `build/W-094-plan-store`.
Build the parts that need neither FIRST (steps 4-6 below with unit tests), then `git fetch origin` and
`git merge origin/build/W-093-kite-reads origin/build/W-094-plan-store` when both exist (check with
`git ls-remote origin build/W-09*`); never edit their files - report a needed change instead.

## What to build (one request = one DB transaction; the order matters)
1. `POST /api/strategies/{strategy_id}/execute`, body `{"action": "ENTRY" | "EXIT"}` (strict, extra forbidden);
   `response_model` an `ApiModel`: `plan_number`, `tags`, `basket_url` (= `KITE_BASKET_URL`), `form_fields`
   (`KiteBasket.form_fields(api_key)`); 404 for a missing / another user's strategy (same answer).
2. Zerodha first: a `get_kite_reads` dependency (mirror `owner_margin_client`; None = not connected -> refuse). Read
   today's orders; `floor` = the highest plan number among tags that `parse_tag` decodes to THIS strategy id; any such
   order whose status is not terminal (terminal = COMPLETE, CANCELLED, REJECTED; any other or unknown word = not
   terminal, fail closed) -> refuse "an earlier basket for this strategy is still open at Zerodha". Then
   `next_plan_number(conn, ..., floor=floor)` (its lock is held to commit).
3. EXIT only: the latest ENTRY plan closed `filled` gives the held legs (none -> refuse, nothing to exit); exit legs =
   the same contracts, opposite side, same quantity.
4. One function `plan_from_stored(saved, catalogue, ...) -> (engine Strategy, ExecutionPlan)` for ENTRY from the stored
   definition (and for EXIT from the held legs), `PlannedLeg.contract` = the catalogue's ZERODHA broker symbol, the leg
   price = step 5's limit. Unit-test it on the real contract.
5. Limits (ADR-080 (3)): per leg `executable_limit(depth_from_quote(quote), side, quantity, tick, planned_price)`;
   quote from a `get_quote_reader` dependency (token -> latest quote mapping with depth, or None). Production: the
   live feed's latest full-mode quote if the app keeps one (find out; say which); otherwise None. No quote, not
   fillable (`depth_too_thin` / `depth_level_off_tick`) or outside the circuit band (`circuit_block`) -> refuse that
   leg with the catalogue message; never a made-up price. `planned_price` = the leg's stored planned entry, else LTP.
6. `ExecutionContext` built from real sources only: `margin_available` / `margin_required` from Zerodha through the
   `KiteMargin` client (#273 - never `margin_estimate_from`); `action` NEW_ENTRY or EXIT; EXIT's `active_legs`,
   `active_version_id` (use `f"plan-{n}"` of the filled entry plan) and `active_legs_hash` computed by the domain's
   own hash function; `reconciliation_blocked_strategy_ids` from Zerodha's positions read (KiteReads) through the
   reconciliation module (`compare` / `blocked_strategy_ids`) - NOT an empty set by default; market open from the
   clock seam and `ofo/timeutil.py`; data health from the quote's age. A field with no real source is `None` (blocks)
   and is named in your report - never `True` to make the gate pass.
7. `eligibility = await fresh_registry(conn, ...)` straight into `check_pre_execution` (never a registry built
   elsewhere); failures -> 409 through the error boundary with the catalogue text (`SafetyResult.failures`).
8. Freeze: `review_freeze_limits(conn, plan)` -> `lambda p: freeze_check(p, limits, today=...)`.
9. `checked_basket(plan, catalogue, plan_number, margin_client=..., freeze_check=...)`; assert
   `type(basket) is KiteBasket`; `BasketRefused` -> 409 with its `user_message`. Built fresh on every request; nothing
   cached.
10. `record_plan(...)` with the basket's orders (tags from the basket, not recomputed), then commit, then return. If
    anything above refuses, nothing is stored (rollback) and no number is consumed.

## Reviewer checklist (each red when mutated; write these first)
- Two concurrent EXIT requests for strategy 1 -> exactly one basket; the other refused (plan_open). Re-press after
  the first is stored -> refused (one open plan).
- Today's book holds OFS1V1L0 with status OPEN (or an unknown word) -> ENTRY refused; COMPLETE -> allowed, floor 1.
- OFS12V3L0 in the book never counts for strategy 1 (exact parse).
- Funds 1 paisa short of Zerodha's required -> 409 with available vs required; nothing stored.
- EXIT with no filled entry plan -> refused; EXIT basket is SELL of exactly the held quantity (reduce-only).
- No quote / thin depth / price outside the circuit band -> refused; never a price from the stored plan alone.
- A context field forced `True` without a source -> a test notices (assert the built context's fields).
- Response money: the basket JSON string is Kite's format; any other money in the response is a 2-decimal string.
- `tests/test_no_order_placement.py` and the margin-only scan `tests/test_margin_from_zerodha_only.py` stay green.

## Rules
- DB tests only through `scripts/orchestrator/db_run.py`, only `tests_app/test_execute_route.py` (after merging W-094:
  `alembic upgrade head` first from your worktree, and after your run `alembic downgrade 0015_audit_broker_allowlist`
  and `alembic current` -> paste 0015; finding branch-migration-tests-move-shared-db). Domain/no-DB tests:
  `python -m pytest -q -p no:cacheprovider tests/test_*.py tests/execution/ tests/marketdata/`. Grep `tests/` and
  `tests_app/` for every route, code and message you touch and add those files. `python scripts/orchestrator/atool.py
  <your worktree> W-095 --no-tests` (read its exit and every ` rc ` line); `python scripts/ruff_ratchet.py` must not rise.
- Commit FIRST `work/W-095.md` (frontmatter shape of `work/W-091.md`: id W-095; title "Execute route: saved strategy
  -> gate -> read-only Kite basket, plan intent stored first (REQ-073 AC-1/AC-2, REQ-055 AC-1)"; requirement_ids
  [REQ-073]; tier A; depends_on [W-093, W-094]; tests_required ['AC-1: tests_app/test_execute_route.py']; core/proof
  = the lines at the top; status in_progress).
- No UI, no return route (W-096), no change to the domain gate's rules. No kit or `spec/` edit, no `views/`, no
  findings INDEX, no regenerated files (the OpenAPI drift file: report it, the orchestrator regenerates), no `evidence/`.
- Commit and push `build/W-095-execute-route`. No PR.
