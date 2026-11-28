STATUS 06:20 | FIELDS READY: cancelled_stops, client_request_id, server_time, now_value, now_as_of, real exits read (see the push sha) | items 1-5 + TE: Passed in cloud (Opus review: see Reviews) | next push: none planned | blocker: none

# Lane FD2: backend replies, fields and closed-market reads

Branch fix/r2-backend-2-1128 (from origin/fix/r2-backend-1128-fd). Paper only; no broker call was made. Local PostgreSQL 16 (a throwaway per-file clone), fakeredis for the key store.

## Per item
| Item | State | Test (count) |
|---|---|---|
| 1 `cancelled_stops` on the order reply (paper door) | Passed in cloud | tests_app/test_paper_orders_r2_fd2.py (4) |
| 1 real door twin | Passed in cloud: the real door prepares a basket, it cancels no stop (a real position has no Stops, ADR-330 (64)); nothing to add there | n/a |
| 1 F4 orphan leg stop revival | Passed in cloud (red first: the stop stayed armed) | test_an_orphan_leg_stop_on_a_flat_contract_does_not_revive_when_the_contract_is_opened_again |
| 2 `client_request_id`, paper door | Passed in cloud (red first: ImportError of `ofo_app.request_key` on the base) | tests_app/test_order_request_key_r2_fd2.py (10) |
| 2 `client_request_id`, real door | Passed in cloud | same file, 2 real-door tests |
| 3 D-1 stored close with no session | Passed in cloud (red first: 5 of 5 failed on the base) | tests_app/test_closed_reads_r2_fd2.py (5) |
| 3 D-2 Positions with no session | Passed in cloud | tests_app/test_positions_route.py (59; 2 changed, see below) |
| 4 `server_time` (exit-state, exit-risk, armed-exits) | Passed in cloud (red first: KeyError on the base) | tests_app/test_fields_r2_fd2.py (3) |
| 4 `now_value` / `now_as_of` on OpportunityOut | Passed in cloud (red first) | test_fields_r2_fd2.py (3); `ofo_app/rule_readings.py` is the store |
| 4 monitoring `expiry_kind_unknown` | Fixed, partly tested: the route side is tested (paused, reason code, badge "Monitoring paused"); the exact sentence needs Lane FC3's catalogue entry and the worker needs Lane FE's publish (see For the owner lane) | test_fields_r2_fd2.py (1 passed, 1 skipped until the sentence lands) |
| 4 real-mode read of armed and fired exits | Passed in cloud | test_fields_r2_fd2.py (2): `GET /real/strategies/{id}/triggers` |
| 5 #877 paper route refuses exit/stop for a real position | Passed in cloud (red first: 201) | test_fields_r2_fd2.py (3) |
| 5 #855 lots refusal on the real door is 409 | Passed in cloud | tests_app/test_real_door_lots_limit.py (2 new) |
| 5 #857 empty chain KeyError | Passed in cloud (red first: 9 failed) | tests/adjustment/test_roll_empty_chain_r2_fd2.py (11) |
| 5 #858 `_tracked_first` | Passed in cloud | tests_app/test_playbook_test_tracked_r2_fd2.py (6) |
| 5 #859 one budget for the Plan watch batch | Passed in cloud | tests_app/test_plan_watch_budget_r2_fd2.py (6) |
| TE tests leave rows behind | Passed in cloud: red 19 failed without the switch, green 57 passed with it, on one database | tests_app/test_db_per_file_guard.py + the two-file run below |
| 3 D-3 four migration 0059 tests | Passed in cloud: the CHECK is right, the tests were wrong | tests_app/test_migration_0059_last_close.py (13) |

## For the owner lane
- Lane FC2 (Positions page, D-2): `GET /positions` with no stored Zerodha session now answers 200 (it answered a red 409 `gate_broker_not_connected`). Fields: `broker_connected: false`; `real_pnl.state: "not_connected"` (a new value beside stated / empty / partial / stale); `real_pnl.reason` and `real_pnl.caption`: the gate's own sentence ("Connect your Zerodha account to continue. ..." as the catalogue renders it); `real_pnl.value`, `real_pnl.pnl_text`, `pnl_text`, `outside_lots`, `excludes_note`: null; `strategies`: []; `has_outside`, `blocked`: false; `blocked_strategy_ids`: []. Every other answer carries `broker_connected: true`.
- Lanes FA2 and FB2 (order reply): `cancelled_stops`: list on the 201 reply of POST /paper/strategies/{id}/orders, one entry per leg stop the request cancelled: `{"leg": "NIFTY 13 Oct 22800 CE", "contract": <contract id>, "level": "120.00"}`; `[]` when none; `[]` on every GET of the book. `leg` is the contract as the book words it, `contract` the contract id.
- `client_request_id` (UUID, optional) on POST /paper/strategies/{id}/orders and POST /strategies/{id}/execute: one UUID per Confirm, sent again with every resend of it. Paper: a repeat of the same key, strategy and orders answers 201 with the book as it is now (the same order ids) and stores nothing; another strategy: 409 "This request key was already used for another strategy."; other orders: 409 "...a different order set."; the first still running: 409 "The first request with this key is still being placed."; key store unreadable: 503 "The app could not check whether these orders were already placed." (no order stored). Real door: a repeat is 409 "A basket was already prepared for this press." (see Decided). A refused first request frees the key. A request with no key behaves as before.
- Lane FD (migration): a durable key store. The key lives in Redis for 600 s (longer than the 120 s unknown window). A crash between the order commit and the key write (milliseconds) can still let one resend through; a table `order_request_keys(user_ref text, key uuid, strategy_id bigint, body_sha256 text, result jsonb, created_at timestamptz, primary key (user_ref, key))` closes it.
- Lane FC3 (explanations.py, new wording for the owner to read): add to the explanation catalogue `monitoring_why_expiry_kind_unknown` = "Every exit rule is not checked because whether this trade expires weekly or monthly is not known." (kind "rule", beside `monitoring_why_unknown`). `routes/monitoring_status.py` already words the code `expiry_kind_unknown` with it as soon as the entry exists (until then the generic "Not being watched: the reason is not known." is shown, never a missing sentence); the skipped test in tests_app/test_fields_r2_fd2.py then runs and pins the exact sentence.
- Lane FE (background.py / monitoring_state.py, the worker): (1) publish `status="paused", reason="expiry_kind_unknown"` in the `/monitoring-state` entry of a trade whose every exit rule answers "not checked" because the expiry kind is "" (adjustment_check R3: `kind = market.expiry_kind or position.expiry_kind`, "" = not known). The route then answers `watch_state: "paused"`, `reason: "expiry_kind_unknown"`, `badge_text: "Monitoring paused"`. (2) once per check cycle call `await rule_readings.publish(client, {(strategy_id, rule_id): value, ...}, at)` (new module `ofo_app/rule_readings.py`, Redis key `ofo:feed:background:rule_values`, TTL 3600 s, no migration) with the value of every rule the worker evaluated, in the units of the record's `value`; the API reads it as `now_value` / `now_as_of` on each record of `/api/adjustment-opportunities`. Until the worker publishes, both fields are null (never the record's own value).
- Lane FC2 / FC3 (Plan watch batch, #859): `GET /api/plan-watch` has one time budget (`BATCH_BUDGET_S` = 15 s) for the whole request; an item the budget cut or never reached has `state: "not_read"` (a third value beside ok / refused) and no `watch`, `refusal` or `status`.
- Lane FA2 / FB2 (exit dialog): `server_time` (aware ISO time, the server's clock) is on `GET /api/market/exit-state`, `GET /paper/strategies/{id}/exit-risk` and `GET /paper/strategies/{id}/armed-exits`; the price age is told against it.
- Lane FC3 (real trades): `GET /real/strategies/{id}/triggers` has the paper read's exact shape (TriggersOut); it reads the same trigger store, which holds rows only for strategies the paper route set stops on (it now refuses a real position, #877), so a real trade answers an empty list unless rows exist.
- Test fix the owner lane may want to know: `tests_app/test_live_login_pickup.py` no longer asserts that a market with no session has no context (D-1 changes exactly that).

## Decided for the owner
- #877 (ADR-330 (64)): "real position" is the one rule `position_kind.kind_of` = real (a held entry, or an order and no paper order). The paper orders route refuses an `exit` order for it and the paper triggers route refuses every stop (409, `real_position_exit_refused`, the text "Real position: exit and protect it in Kite. Stops and alerts here cover paper trades only."). An unknown kind is not refused here (the paper store answers by its own rules): refusing it would block a paper exit whenever one read fails.
- #855: the real door's lots refusal now has the code its other refusals have (409); the paper door keeps its 422 (the lots rule and sentence are the one shared function).
- #857: an empty chain beside a stated spot answers the existing "{leg} has no price, and this approach trades it." refusal (no new wording); an expiry kind the target-delta table does not hold answers `adjust_roll_basis_unreadable`.
- #858: only `TrackedUnreadable` (and its `TrackedExited`) read as "not of the type"; any other fault, a database error included, is raised so the preview shows it.
- #859: the batch budget is 15 s for the whole request (under the browser's 20 s); a cut or unreached row is `not_read`.
- Item 4 `now_value`: the brief's "worker's last stored reading" has no store today (REQ-165 AC-6 "the screen's GET reading the worker's latest result" is named as not built in background.py). I built the reading side and its store contract (`rule_readings.py`) and left the publish call to Lane FE; null until then.
- TE (tests leave rows behind): root cause: a few files (test_clock_ahead_records, test_last_leg_closes_alerts and every file that seeds through `test_background_worker._seeded`) commit strategies, catalogue rows and orders on their own sessions; no guard lets a test delete them (DELETE/TRUNCATE are refused even for the owner), and a file run later on the same database meets them ("would drop 750 of 750 live NIFTY contracts", an extra `lapsed` alert). The per-file database copy already exists (GC-MERGE1 #649) but ran only for a db_run_fresh throwaway or in CI. Fix of the class: `OFO_TEST_DB_PER_FILE=1` (tests_app/conftest.py `should_clone`) gives every file its own copy of a disposable database. Proof: `test_clock_ahead_records.py` then `test_paper_order_lots_limit.py` on one database: 19 failed without the switch; with it these two plus test_last_leg_closes_alerts, test_paper_settlement and test_db_per_file_guard: 57 passed, and the template database held 0 strategies afterwards. The shared `ofo_test` that also serves production still must not be cloned: there keep running ONE file (CLAUDE.md).
- D-1 (spec basis ADR-330 (63), ADR-212, ADR-008): with no stored session the market now keeps a socket-less book (provider built from the catalogue, no Kite call, state stays not connected), so the existing last-close task seeds it while the market is closed and every screen reads the stored close with its own date and time. The same after Disconnect. Contracts and the Option Chain read the same book. Never read while the market is open (unchanged). A catalogue that cannot be read leaves no book and the screens say prices are not available.
- Real door repeat (ADR-017, ADR-016 to ADR-019): the brief says a repeat returns the first result. On the REAL door the result is a sealed Kite basket form; handing the browser the same form twice could send the same orders to Kite twice, and the sealed `BasketPost` is built only from a checked basket. Decision: a repeat of the same key is refused with a stated reason and prepares nothing; the page opens the plan to see the basket. The paper door returns the first result as asked.
- Key store (no migration): Redis, TTL 600 s, key scoped by user. An exception whose outcome is unknown (a failed commit, a failed read after the commit) leaves the key claimed until it expires, so a resend is told "still being placed", never placed twice.
- `cancelled_stops` lists only the stops the request cancelled that were armed on a contract the book held open before it (a move or an exit). An old orphan (armed on a flat contract) is cancelled quietly before the fill (F4) and is not listed: it is not something this move removed.
- D-3: migration 0059's CHECK is right (psql on PostgreSQL 16 answers 23514). The tests passed a text value for a timestamptz parameter; asyncpg refuses that on the client with 22000 before the CHECK runs. The tests now pass datetimes.
- D-2: the Real part's "not connected" sentence is the existing gate sentence (no new wording); the page may print `real_pnl.reason`.

## New wording for the owner to read
All in `backend/ofo/errors/templates.py` (pins in tests/errors/template_pins.json, "pending owner read"):
1. request_key_other_strategy (STRATEGY_VALIDATION_580): "This request key was already used for another strategy." / "No order was stored; one request key belongs to one set of orders on one strategy." / "Placing these paper orders." / "Press Confirm again to place the orders with a new request key."
2. request_key_different_body (581): "This request key was already used for a different order set." / "No order was stored; a repeat of a request must carry the same orders as the first." / "Placing these paper orders." / "Read the strategy's orders, then press Confirm again if you still want them."
3. request_key_in_progress (582): "The first request with this key is still being placed." / "No order was stored by this repeat; the first request decides what is stored." / "Placing these paper orders again." / "Wait a moment and read the strategy's orders before you try again."
4. request_key_store_unavailable (583): "The app could not check whether these orders were already placed." / "No order was stored; with the check down, a second copy of the same order could be stored." / "Placing these paper orders." / "Read the strategy's orders to see what was stored, then try again."
5. request_key_already_prepared (585): "A basket was already prepared for this press." / "No new basket was prepared, so the same orders cannot be sent to Zerodha twice from one press." / "Preparing this basket again." / "Open this strategy's plan to see the basket that was prepared."
6. real_position_exit_refused (584, used by #877): "Real position: exit and protect it in Kite." / "Stops and alerts here cover paper trades only." / "Exiting or protecting a real position here." / "Use Kite to exit or protect this position."

## Files touched outside the May-edit list (and why)
- backend/ofo_app/request_key.py (new module for item 2; one module per capability, shared by the two doors).
- backend/ofo/errors/templates.py and tests/errors/template_pins.json: the six refusal sentences above (a refusal needs a catalogue text; explanations.py was not touched).
- tests_app/reply_inventory.py: regenerated by its tool (new reply fields).
- tests_app/test_place_orders_pool_r2_fd.py, test_request_seq.py, test_connect_gate_routes.py: call the routes directly; they take the new `keys` argument.

## Not done
Nothing of the queue. Open: the worker's publish of `rule_readings` and of `expiry_kind_unknown` (Lane FE), the catalogue sentence (Lane FC3), the durable key store (Lane FD, migration). The ruff/E501 and I001 of pre-existing lines were not touched.

## To file as deferred issues
- The paper door's `client_request_id` replay returns the book as it is NOW with the first request's `cancelled_stops`, not a byte copy of the first 201 (prices move); a durable copy needs the table above.
- `strategy_store.kinds_of` swallows a database error inside the shared session (an aborted transaction then fails the next statement): the class of #858 in another place.

## Reviews
Opus review of items 1, 2 and #877 (read-only reviewer, Tier A): see the section at the end of this file ("Opus review").

## PC steps
- Market closed: restart the API with LIVE_MARKET on and no Zerodha login. GET /api/market/indices should answer the 27 Nov close with its own date and time; Home and the Option Chain show the stored closes. GET /positions answers 200 with `broker_connected: false`.
- Live: no step for items 1 to 3.

| task | model | minutes |
|---|---|---|
| items 1 to 5, TE (build, tests) | Sonnet (this session) | 130 |
| Opus review of items 1, 2, #877 | Opus (reviewer) | see below |
