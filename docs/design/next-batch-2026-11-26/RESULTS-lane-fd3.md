STATUS 09:50 | items 1, 2 (kept) and 3, 4, 5, 6, 8 (dropped by the 09:25 cut but ALREADY DONE here: Lane FD4 skips them) fixed, not tested live; gate on the pushed head; item 7 and the 09:12 additions (cancelled_stops from returned ids; real position's old armed stops shown as not applicable) NOT done | blocker: none

# Lane FD3 RESULTS (backend, third batch)

Branch: fix/r3-backend-3-1128, from fix/r2-backend-2-1128 plus origin/integration/weekend-r2-1128 (alembic head 0060, now 0061).
Highest status claimed: "Fixed, not tested" (live). Database tests ran on a local PostgreSQL 16 clone, one file at a time.

## Core and proof (items 1 and 2)

- Core: a user exit on a held strategy is refused (409 `real_position_exit_refused`), and the request key survives a crash
  between claim and commit.
- Proof, item 1, red on the base (HEAD a99035d, same test, held strategy, legs [2], `paper_orders` before = after + 1):
  `FAILED tests_app/test_exit_door_real_fd3.py::test_i158_a_tracking_exit_on_a_held_strategy_is_refused_and_nothing_is_stored`
  `assert 200 == <HTTPStatus.CONFLICT: 409>` (the exit was stored).
  Green after the fix: `python -m pytest -c pytest-app.ini tests_app/test_exit_door_real_fd3.py` -> `5 passed`.
  (The brief's legs [1] is already exited in the fixture book, so the test uses leg 2, the open one.)
- Proof, item 2: `tests_app/test_order_request_key_durable_fd3.py` -> `8 passed`: a crash between claim and commit stores neither
  (claim rolled back, key free again); two presses, one key: the second waits for the first and then gets its stored result
  (`Repeated`), one row; a repeat after a Redis `flushdb` still answers 201 with the same order ids; the app role cannot
  DELETE or rewrite `body_sha256`.

## Done

| # | Item | Result | Test (file) |
|---|------|--------|-------------|
| 1 | I-158 user exit on a real or unknown position | `paper_limit.refuse_real_exit` is called by `place_checked` (the one write) and early by `exit_tracking`; kinds `stop`/`settle` never go through it. `cancelled_stops`: the armed set is now read under the strategy row lock (`lock_strategy` before `_armed_leg_stops` in `_place_orders`) so no other lock-taking writer can cancel between that read and the read-back | tests_app/test_exit_door_real_fd3.py |
| 2 | Durable request key | migration 0061 `order_request_keys`; `request_key.lookup / claim_in_transaction / finish_in_transaction`; paper door and real door claim in the orders' own transaction; lookup is first (the table is the record of truth), Redis stays the fast path for "still being placed" (582) | tests_app/test_order_request_key_durable_fd3.py, test_order_request_key_r2_fd2.py (12 still green) |
| 3 | `kinds_of` swallowed errors | a failed read now raises `SQLAlchemyError` (no "unknown for every id") | test_exit_door_real_fd3.py::test_item3 |
| 4 | Connection held across waits | real door: `_off_loop` releases before every Zerodha read (orders, bands, positions, margin x2, basket); return: Zerodha reads and the entry-facts market read happen before the lock, `_return` re-reads plans under the lock and refuses on a changed tag set; `_refuse_take_profit_at_loss` releases first. Left on purpose: `record_basket_facts` (see "For the owner lane" and "Question for the owner") | tests_app/test_execute_return_pool_fd3.py |
| 5 | Pool scan | builds its own list, checks EVERY wait (nearest earlier event must be a release; round a loop), WAIT_NAMES widened; found `_place_orders` (2 waits): one fixed, one allowlisted with its lock and proof; GUARDED_COUNT 13 | tests/test_pool_release_before_market_wait.py (mutation: removing the release in `_place_orders` turns it red, shown) |
| 6 | Failing database tests | see the table below | |
| 8 | Plan acceptance leftovers | F7 fixed (plan read under the lock inside `work()`; test red before: `'50' == '35'`, a lost update); F5 decided (below) | tests_app/test_plan_accept_routes.py |

### Item 6, case by case (product defect or test out of step)

| Test | Cause | Verdict |
|------|-------|---------|
| test_execution_return `test_real_first_fill_stores_entry_facts_once` | the fake index quote had no `.health`; ADR-330 (39) judges the spot "live" only when AVAILABLE | test out of step; fixed (also passes with the item 4 change) |
| test_route_latency_budget (4) | each adjustment route runs ONE more statement: the stored expiry-kind read (`_stored_kind_or_empty`, commit b00d304). Measured: with it stubbed the counts are 23 / 19 / 18 again | needed for correctness (the kind decides the stop rows; unknown fails closed); ceilings +1 with the reason in the test |
| test_slow_price_source_live_day | 3 strict xfail marks passed (hotfixes landed): marks removed. The 2 timeouts: the scenario's frame is a usable feed tick, `index_spot_of` (1) then makes no REST call, so the stalled REST reader was never reached | test out of step; the feed has no tick on the first pass in the test |
| test_pool_not_held_across_market_wait (2) | same cause as the line above | same fix, in the shared fixture |
| test_d36_adjustment_counts | goldens carry `strategy_id: 1` | the id is normalised in the reply compare |
| test_adjustment_history_why | the third basket is over the plan's maximum 2 (ADR-318 (5)); only a reducing basket is accepted | test out of step: that basket reduces; the T-03 row is read at index 1 |
| test_alert_routes (2) | new fields `position_kind`, `position_kind_text` (ADR-330 (64)) | key sets updated |
| test_d38_page_counts | additive labels and `put_back` lists on the plan reply | golden regenerated (diff = 5 added lines only) |
| test_pinned_clock | the reply names the list's day (database clock), not the pin | the day is read back from the database |
| test_risk_exit_not_gated | the closed trade lapses its open record `strategy_closed` (paper_exit) | test out of step: asserts `lapsed` after the exit fired |

Note for PC runs: committing tests (this lane's key file, d36) leave rows that are never deleted. A used template gives
false failures (T-03 not flagged: records of an earlier seed). Run on a clone (db_run.py), as the brief says.

## For the owner lane

- Lane FR, `adjustment_readers.record_basket_facts` (called in the fill's transaction by `routes/paper.py::_place_orders`):
  it waits on the feed (`_index_spot_held`, `_snapshot`) while the transaction holds the strategy row lock and a pooled
  connection. Split it: `read_basket_market(ctx, feed, underlying, kept_ids, prices_not_live_confirmed)` (all waits, no
  `db`) and `store_basket_facts(db, strategy_id, book, clock, market)` (database only). Then `_place_orders` calls the
  first before `lock_strategy` and the second where it calls `record_basket_facts` now. After that, delete the allowlist
  entry `('paper.py', '_place_orders', 'record_basket_facts')` in tests/test_pool_release_before_market_wait.py.
- Lane FC3, item 7: `ofo/errors/explanations.py` needs two templates (new wording below); `ofo_app/exit_market.py::exit_market_answer`
  returns them beside the exit sentences; `routes/exit_market.py::ExitMarketOut` gets `entries_sentence: CatalogueText | None`.
- Lane FJ: the Add to Paper dialog must show `entries_sentence` (not `sentence`, which says "Exits") once the field exists.

## Decided for the owner

- F5 (a PUT without `accept` on a plan with no playbook pointer, naming a playbook): KEPT. The plan's own body and its
  `accepted_at` do not change; only the pointer is set, and only from NULL (a pointer to another playbook still needs
  `accept`). This is the owner's LJ-2 option 1 and REQ-158 AC-5; reversing it would break a stated rule. Already pinned by
  `test_a_put_on_a_null_playbook_plan_with_the_prefill_keeps_accepted_at_and_its_own_stops`.
- Redis down or unreadable: the keyed request is still refused (503 583) as before; the table does not replace that check
  (a keyed request needs both). A repeat that the table already knows is answered without Redis.
- The real door's claim sits right before `record_plan`, after every Zerodha wait, so a refused review leaves no key.
- `record_plan` re-locks the strategy and re-checks (open plan, number above the highest, tag taken), so releasing the
  connection earlier in the real door does not weaken the double-order guard: a second press that raced past is refused
  there (`gate_dependencies_unsatisfied`).

## New wording for the owner to read

- Item 7 (not built): "The market is closed. Orders can be placed from 09:15 on <day>." and the no-day form "The market is
  closed. Orders can be placed when it opens." (sentence beside the owner's exit wording, which is unchanged).

## Question for the owner

- `record_basket_facts` holds the strategy lock and a connection for one feed hold (about 3 s plus two feed waits) because
  ADR-283 (1) says the facts are stored in the fill's transaction. Recommendation: read the market before the lock and
  store the facts under it (the split above), keeping one transaction; the facts are then those of a moment slightly before
  the fill. This is the owner lane's file and a product reading of "the market at this basket's fill", so it is listed, not decided.

## Not done

- Item 7 (`entries_sentence`): the typed sentence door accepts only a catalogue template (a plain string is refused at
  validation), and the templates are in a file this lane may not edit. No route-local build is possible. Exact change above.
- Item 9 (fd2 F7 route tests, UX-A08 plan-read measurement): not started in this push.
- Item 4, `record_basket_facts` (see above): left, allowlisted with its lock and proof.

## PC steps

Market closed: (1) back up, `alembic upgrade head` (0061, additive: old code runs against the migrated database, it never
touches the table); (2) run `python scripts/orchestrator/db_run.py . python -m pytest -c pytest-app.ini tests_app/test_order_request_key_durable_fd3.py` (one file; it commits a strategy row, run on a clone); (3) press Confirm twice on a paper order with one
`client_request_id` (the page sends it): one set of orders.
Live: repeat with the feed on; flush the Redis key (`redis-cli flushdb`) between the presses: the second still answers
201 with the same order ids; try an exit on a held (real) strategy: 409 with "Real position: exit and protect it in Kite."

## Tasks / model / minutes

| task | model | minutes |
|------|-------|---------|
| items 1-6, 8 build, tests | Sonnet (this lane) | about 45 |
| Opus review of items 1, 2, 4 | Opus | pending |

## Opus review (items 1, 2, 4): REVISE, then fixed

- F1 MAJOR (fixed): on the production tracked-reader shape, `adjustment_readers.stored_kind` rolls the request session back
  on a catalogue read failure, which dropped the claim and the lock; the orders then committed with no key row, and the same
  key placed twice after a Redis flush (reproduced by the reviewer, 3 -> 4 orders). Fix (structural): `finish_in_transaction`
  requires exactly one row updated, else rolls back and answers 583 (no orders stored). Test:
  `test_a_claim_lost_to_a_rollback_refuses_and_stores_no_orders`. Class fix for the owner lane (Lane FR file):
  `stored_kind` must wrap its catalogue load in `async with db.begin_nested():` instead of `db.rollback()`, so it never
  rolls back a caller's session. The test harness overrides the tracked reader with its own session, which hid this; a route
  test on the production reader shape is not added (not done).
- F3 (fixed): the real door now takes the strategy lock before the claim (same order as the paper door).
- F2 MINOR (not done): after the release, `record_plan` does not re-check adopted holdings or the strategy revision (W-151
  runs before the lock). Fix: re-read `adopted_for` and the revision under the lock and refuse if changed. Listed, not built.
- F4 MINOR: a failed kind read answers a plain 500 (still fails closed, nothing stored); a catalogue sentence is not built.
- F5 MINOR (unverified): a strategy with only execution plans may answer 404 before the 409 on the tracking exit.

## After the 09:25 cut

Done before the cut and pushed here, so Lane FD4 does not redo them: item 3 (`kinds_of`), item 4 (real first fill connection
release, except `record_basket_facts`), item 5 (pool scan), item 6 (Lane TE database tests, table above), item 8 (F5 decided, F7 fixed).
Not done: item 7 (see above) and the two 09:12 additions: (1) `cancelled_stops` from the ids the cancel UPDATEs return (now it is
read back under the strategy lock; the stale-stop cancel inside `paper_store.place` returns no ids and that file is not mine);
(2) a real position's old armed stops must read "not applicable: real position" in `GET /paper|real/strategies/{id}/triggers`
and `routes/plan_watch.py`. Question for the owner: should such rows be cancelled or kept and shown as not applicable?
Recommendation: kept and shown as not applicable (nothing is removed without the owner).

SAFE TO CLOSE: not yet.
