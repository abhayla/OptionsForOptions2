STATUS 14:50 | push 1 on origin (N1 closed f0448902); push 2 = this head: 2a 2b 2c 2d 2e 2f 2g, 3.2 to 3.7, F3 nit, item 4, W-13, N5, N7, W-28, Opus review done and its fixes in | next: plan-watch 9-row cost, N8 | blocker: none

# RESULTS Lane FD5 (backend leftovers of FD3, FD4, FR; every database test)

Branch `fix/r3-backend-5-1128` on `fix/r3-backend-4-1128` + `fix/r3-backend-3-1128` + `fix/r3-readers-1128`
(one merge conflict, tests_app/test_execution_return.py `_market`: both sides built the same fake quote with
`health=AVAILABLE`; kept one, `DataHealth` from `ofo.rules.inputs`, the module `ofo.marketdata.quote` itself imports it from).
Status: Fixed, not tested on the PC.

## Item 1: every database test, each file ALONE on a fresh database (`OFO_TEST_DB_PER_FILE=1`, role `ofo_app`, limit 5, no proxy)
Run on the merged branch before any change (Core proof): 13 of the 15 files green; the 2 below failed.

| File | Test | Cause | Fix or reason left |
|---|---|---|---|
| test_adjustment_history_why | 2 tests | none now: green (2 passed) | FD3/FD4 fixed it |
| test_alert_routes | all | none now: green (10 passed) | FD3/FD4 fixed it |
| test_d38_page_counts | all | none now: green (5 passed) | fixed |
| test_execution_return | all | none now: green (42 passed) | fixed (stub quote now has `health`) |
| test_pinned_clock | all | none now: green (37 passed) | fixed |
| test_risk_exit_not_gated | all | none now: green (9 passed) | fixed |
| test_slow_price_source_live_day | all | none now: green (10 passed) | fixed |
| test_background_worker | all | green (33 passed). TF's TooManyConnectionsError did not appear | not reproduced; role limit 5 is set in this container as in CI |
| test_egress_gate_doors | all | green (27 passed) with the proxy variables unset | the earlier failures were the container's outbound proxy (environment); CI has none |
| test_migration_0059_last_close | all | green (13 passed) with the proxy unset | same: environment (proxy) |
| test_route_latency_budget | `test_query_ceiling[plan-watch]`, `test_batch_plan_watch_query_ceiling` (25 statements, ceiling 24) | WRONG TEST (ceiling out of date). FD3 round 2 (R6, ADR-330 (64)) added `strategy_store.kinds_of` to `plan_watch._armed_lines` (one statement when the strategy has armed rows). Measured: with `_stored_kind_or_empty` stubbed the batch of one row counts 24 (FD3's first measure was 23), so the kind read is the only added statement; FD3's own head fails the same way (25 > 24) | plan-watch ceiling 24 -> 25 with the reason in the test; the other three ceilings unchanged; 7 passed, 1 xfailed, twice in a row |
| test_route_latency_budget | `test_single_route_budget` | ENVIRONMENT: a wall-clock bound (200 ms warm) failed once on the first, cold run in the fresh container; green on two later runs | left as is (timing, 4-core container) |
| test_pool_not_held_across_market_wait | `test_thread_executor_stalled_by_broker_reads_does_not_slow_health_or_the_paper_read` | INTERMITTENT, environment: failed on the first (cold) run of the file, passed on 8 later runs (6 whole-file, 2 alone). Its only bound is `/health` within 0.5 s while 20 plan-watch requests (about 100 ms CPU each) run on a 4-core box | not changed; failure message not captured in full (tail only) |

## N1 (coordinator, second Opus review of round 2): no paper order on a real position
Core: red first (4 of 5 new tests failed: an `open`/`add` was stored on a sent basket, 201). Fix, in the one door every
paper order passes: `paper_store.place` (all user kinds; `stop` and `settle` are the server's and pass) asks
`strategy_store.paper_order_refused`: an unreadable kind refuses; a real position with NO held entry (a basket sent, no
paper order) refuses every kind, so an order can never turn its kind from real to paper; a held entry refuses only an
`exit`. `paper_limit.refuse_real_position` (was `refuse_real_exit`, alias kept) calls the same function earlier.
Tests (tests_app/test_exit_door_real_fd3.py, 5): held add and exit, the store's open on a sent basket (kind stays
real), the order route 409 with the real sentence, unknown refuses, paper/none/settle still place.
Regression: every tests_app file that touches the paper store (89 files, each alone) was run: 2 red, both explained
below, fixed.
- test_held_entry `test_exit_and_add_orders_on_a_held_condor...` was already red on FD3's head (the I-158 exit refusal):
  the test expected an exit on a held condor to be stored. ADR-330 (64) says no exit; test now expects 409 for the exit
  and still records the add.
- test_held_tracking k13 closed a held condor with `exit` orders through the store; now closes with `settle` (the
  server's kind).

## Decided for the owner
- Held condor (ADR-292 (4)): `add` and `open` stay recordable (kind stays real, held row decides); only `exit` is
  refused (ADR-330 (64)). Reason: the one way the app learns a broker change is the paper forms.

## Question for the owner
- A clash: ADR-292 (4) "The user records each change with the existing paper order and exit forms" vs ADR-330 (64) "a
  real position has no exit in the app" (and the coordinator's N1 text "every paper order action on a real position is
  refused"). I kept add/open on a HELD condor and refused its exit (the later rule). Recommendation: keep it; if the
  owner wants no recording at all, a held condor can never be corrected after a broker change.

## Opus review of N1 (f21b59f4): PASS, no open path (store, place_checked, route models, race under the strategy lock read)
Fixed here: the stray `dump.rdb` removed (F6); held `open` now has a test (F5). Left, listed:
- To file as deferred issues: (F1, MAJOR, existed before) the monitor still fires a paper `stop` on a held (real)
  position when a stop was armed before #877 (paper_monitor.py reload has no kind filter; paper_store.place lets `stop`
  through); it could close the strategy while the position is open at the broker. Needs a read-only count of armed
  triggers on strategies with a held row, and the owner's call (cancel them or filter in `reload`; R6: nothing is
  removed without him). Not mine (paper_monitor.py is Lane FE3's file).
- (F2, MINOR, order path on only) a paper order placed first and a basket sent after reads as paper (`kind_of`).
- (F3, MINOR) any execution plan row, even an unsent form, blocks paper orders on the strategy, with the Kite sentence.
- (F4, MINOR) the refusal code `real_position_exit_refused` is shared by open, add and exit refusals (logs).
- (F7) the cited ADR-330 (64)/(58) text is on origin/fix/ic-live-test-1123, not this branch; the held rule has no decision row.

## Push 2: what was built (each item: test red first, then green; every touched test file run alone, one fresh database)
| Item | Result |
|---|---|
| 2a cancelled_stops | `paper_store.place(..., swept=[])` returns the ids of its stale-stop sweep (`UPDATE ... RETURNING id`); `routes/paper.py::_cancel_leaving_stops` unions them with the ids `paper_trigger_store.cancel` returned: no read-back. Opus F2 fixed: the sweep's conditions are on the UPDATE's own row (no self-subquery), so a stop another tab cancelled a moment earlier is not named. Tests: tests_app/test_order_routes_fd4.py (swept ids; a fired one not named) |
| 2b entries_sentence | tests_app/test_exit_market_adr330_60.py green (8). For FE3: templates `exit_market_closed_entries` ("Orders can be placed from 09:15 on {day}.", value `day`: DayLabel) and `exit_market_closed_entries_no_day` ("Orders can be placed when it opens."), kind `values_seen` |
| 2c Execute and Return re-read | adopted holdings and the strategy revision are re-read under the strategy lock (Execute: `_refuse_if_changed`, before the claim; Return: in `_return`); changed -> 409, nothing stored. Execute says `execute_plan_changed`; Return says `gate_broker_unconfirmed` because the Execute sentence ("no order was prepared") is false at Return (Opus F1). Wording need for FE3 below. Tests: test_execute_revision.py, test_execution_return.py (4 red-first) |
| 2d failed kind read | `strategy_store.paper_order_refused`, `routes/paper.py::_refuse_real_position`, `routes/alerts.py::active_alerts` answer `user_input_request_not_available` (503) with nothing stored; no new wording needed. plan_watch already did (pin test) |
| 2e F5 | real: a plan-only strategy answered 404 before the 409. tracking exit now refuses a real or unknown position first (test_exit_door_real_fd3.py) |
| 2f stored_kind rollback | the catalogue load runs in `begin_nested()`, never `db.rollback()`; the claim and the strategy lock survive; route test on the production tracked-reader shape (test_order_request_key_durable_fd3.py: 201, orders stored, key row done) |
| 2g R9 real door, R6 plan-watch half | Execute refuses `store_busy` past 8 s before the commit, nothing stored, key freed (test_execute_revision.py); plan-watch armed lines of a held or unknown position read `not_applicable` with the position-kind sentence, no price, no distance: pinned (they already were; no code change) |
| 3.2 | tests_app/test_worker_heartbeat.py holds `monitoring_state.CLOCK_SKEW_S == feed_bus.HEARTBEAT_SKEW_S` |
| 3.3 | `routes/paper.py::entry_facts(feed=)` and the Return door (new `get_live_feed` dependency) pass the route's feed to `entry_facts_now`; tests in test_entry_not_live_confirmed.py and test_execution_return.py |
| 3.4 | `_index_spot_held` answers `(spot, at)`; `BasketFacts.spot_at` carries it. NOT stored: a column needs a migration (not built; old code would run against it) |
| 3.5 | `feed_bus.HeartbeatReader` notes when the stamp last CHANGED by the reader's clock (unchanged > 120 s = stale); `worker_watch` uses it. The page status (`monitoring_state.read_states`, FE3's file) still uses the stamp-only judge |
| 3.6 | `adjustment_check.state_of` runs `stops_of` also for an unknown kind (an IC's 2x-credit stop gets a result; days_left stays None); red-first in test_ictrack_state_inputs.py |
| 3.7 | tests/test_price_reads_one_door.py keys a closure by its full path (`outer.inner`); `_index_quote_held.read` has its own `awaiting_phase_8` exemption; the old `read` entry became `held_read.read` |
| F3 nit | `_t10b` with an unknown kind and no value in any stage is "not checked" (`adjust_trigger_no_expiry_values`), never a flag |
| ceilings | the savepoint of 2f costs two statements per kind read: ceilings plan-watch 25->27, adjustment-check 20->22, adjustment-plan 19->21 (paper book 11 unchanged), reason in the test; a further statement still fails. On a tunnelled database that is two more round trips per request: the price of keeping the order claim and lock |
| item 4 | `catalogue_store.load_catalogue(conn, name)` reads one underlying's rows; `stored_kind` uses it; pinned in test_plan_read_cost_fd4.py. Statement counts unchanged (one read either way), so no ceiling lowered; the saving is rows (about 4,700 -> one underlying) |
| W-13 (coordinator) | `alert_title.labels` ran `nearest_expiry` once per strategy: 62 statements for 12 strategies on /api/alerts/answered; now ONE batched read (`adjustment_readers.nearest_expiries`): 6 for 2 and for 12; /api/alerts/active 2. Test in test_alert_routes.py. (Helper-built, I re-ran test_alert_routes: 11 green.) Real-book strategies still read alone (a few statements each) |
| W-01 / O-R-09 | NO server fault: the saved Stop (Rs) 100 is in the sheet body and in the check limits (two pin tests in test_adjustment_plan.py). The plan block is `frontend/src/components/strategy/PlanEntry.vue` and prints from the check's `limits` rows: Lane FJ |
| O-R-07 | the sentence `paper_exit_less_protected` builds its legs with `display_contract` ("NIFTY 1 Dec 25600 PE"); pin test in test_paper_exit_risk.py. An ISO date on the PC = a build before 3f63b160b, or a frontend string (FE3/FJ) |
| O-P-03 | NO server fault in the status word: a running paper trade reads Running on all four routes with no market context (pin in test_strategy_tracking.py). "Draft - Live data not connected" is the outcome route's no-provider label |
| N5 | the paper door's 8 s deadline now counts from the request's entry (test red under the old start). Its own plain reason needs a new sentence: FE3 below |
| N7 | `_triggers_out` runs after the commit: a failed kind read reads `unknown` (lines fail closed), answer 201, never a 5xx (test_exit_door_real_fd3.py, red under mutation) |
| N6 | = 2f |
| W-28 | `plan_rupee_loss` reads "Plan loss stop" (one loss stop however typed, ADR-330 (5)(a)); test_alert_reason_words_r2_1128.py. New wording: pending owner read |
| Environment | tests_app/test_kite_broker_reader.py `test_attack2...` fails only with the container's outbound proxy variables set; green with them unset (100 passed) |

## Opus reviews
- N1 (f21b59f4): PASS (above).
- Push 2 (c71f3b3c3, read-only): REVISE with 1 MAJOR, fixed here: F1 Return said "no order was prepared" (false, a plan exists) -> now `gate_broker_unconfirmed`; F2 (sweep named a stop another tab cancelled mid-statement) fixed; F5 comment fixed. Left, listed: F3 the plan route's `_stored_kind` passes the full-catalogue `load=load_catalogue` while the live check reads one underlying (one unreadable SENSEX row would block a NIFTY plan read but not its check; agrees on clean data); F4 the page status keeps the stamp-only heartbeat judge (FE3's file) and the reader uses the wall clock (a backward step lengthens fresh); outside the diff: `position_kind.kind_of` says PAPER when a strategy has a plan AND paper orders (Execute does not check for paper orders) - to file as a deferred issue.
- Not reviewed (read-only, listed by the reviewer): W-13 batch, 3.4, F3 nit, the allow-list edits.

## For the owner lane
- FE3: templates.py: (a) `exit_market_closed_entries` and `exit_market_closed_entries_no_day` (texts above, kind `values_seen`); (b) a Return-door sentence for "something changed while you were at Kite": e.g. "Something changed while you were away, so nothing was recorded. Press Return again." (Return now uses `gate_broker_unconfirmed`); (c) N5: a plain reason for a request that ran past the server deadline, e.g. "This took too long, so nothing was changed. Try again." (the code still says `store_busy`, "busy with another action", the wrong cause); (d) `_trig("expiry_kind_unknown", ...)` "Not checked: this trade's expiry type (weekly or monthly) is not known, so the percent stop has no value." with stop_lines.py `NOT_CHECKED[EXPIRY_KIND_UNKNOWN] = f"{_T}expiry_kind_unknown"`; (e) monitoring_state.py `CLOCK_SKEW_S: Final = 5` becomes `feed_bus.HEARTBEAT_SKEW_S`, and `read_states` uses `feed_bus.HeartbeatReader` (a held instance) instead of `read_heartbeat_state`; (f) FD4's six `monitoring_why_<code>` sentences: index_not_live, leg_not_live, exit_not_priced, index_exits_not_run, exits_not_checked_yet, expiry_kind_unknown.
- FE3 (O-P-03): routes/outcome.py ~line 1351 and ofo/outcome/service.py `not_connected` / `_not_live_label` (~line 411): for a strategy with orders, do not word the answer "Draft - Live data not connected"; say prices are not live and give the stored close with its time; needs a new catalogue sentence (e.g. `outcome_running_not_live`).
- FJ: PlanEntry.vue prints stop and target from the check's `limits` rows: the saved Stop (Rs) 100 is there; the page's 10 s client timeout (W-13) and the 20 s plan-watch batch window (lib/planWatchBatch.js:13).

## Decided for the owner
- Held condor (ADR-292 (4)): `add` and `open` stay recordable, only `exit` is refused (see N1 above).
- 3.5: unreadable -> fresh still sends "running again" (ADR-286 text lists it); the false-fresh is closed by the change-tracking instead.
- W-28: "Plan loss stop" for a rupee loss stop (FE3's recommendation; ADR-330 (5)(a)).
- Return refusal sentence: `gate_broker_unconfirmed` until FE3 adds one (true statement beats the exact one).

## New wording for the owner to read
- "Plan loss stop" (alert reason line for a loss stop typed in rupees; was "Plan rupee stop"). No other new on-screen sentence was added; the proposals under FE3 above are not in the catalogue yet.

## Question for the owner
- ADR-292 (4) (a held condor's broker changes are recorded with the paper order and EXIT forms) vs ADR-330 (64) (a real position has no exit in the app). Built: add and open recordable on a held condor, exit refused (409). Recommendation: keep; if no recording at all is wanted, a held condor can never be corrected after a broker change.
- `record_basket_facts` split (ADR-283 (1) says the facts go in the fill's transaction; the pool rule forbids a feed wait in it): not built, a clash; its allowlist entry stays.

## To file as deferred issues
- Monitor fires a paper `stop` on a held (real) position when a stop was armed before #877 (paper_monitor.py `reload` has no kind filter; `place` lets `stop` through); could close the strategy while the position is open at the broker. Needs a read-only count of such triggers and the owner's call (R6).
- `position_kind.kind_of` answers PAPER for a strategy with both a plan and paper orders; any plan row blocks paper orders on the strategy with the Kite sentence; the shared refusal code `real_position_exit_refused` for open/add/exit.

## Not done
- Coordinator item 2 (plan-watch 9 rows inside the budget): NOT fixed. I measured one candidate cause, a catalogue read per row for the kind, and it is not there: with the scenario provider the rows take the kind from the market read, so a per-request memo changed nothing (built, tested red-less, reverted: commits 0609564e/234b064f). Per row the cost is about 25 statements and about 100 ms compute here; on the PC (tunnel latency, 2.7 s per row) the statements are the cost. Next: batch the per-row reads (one orders read, one contracts read, one settings read for all rows) the way W-13 did for the alert labels.
- N8 (narrow the key table's grants, add expiry): needs a migration; not built.
- `spot_at` is not stored (column).
- test_pool_not_held thread test: intermittent on a cold first run; no change.
- Second gate: see STATUS.

## PC steps (paper only; market closed, then live)
- Closed: open Alerts > History with 10+ answered alerts: loads in about a second; a rupee loss stop alert reads "Plan loss stop"; in a held condor (Held at my broker) record an add: stored; try Exit: refused with "Real position: exit and protect it in Kite."; a real position (basket sent) refuses any paper order.
- Live: place a first paper basket with the feed down and the "prices are not live" tick: stored with the held index value; run Return after a first fill: first-fill facts stored once; put a stop on a leg, close that leg: the reply names the stop once.

| task | model | minutes |
|---|---|---|
| env set-up, item 1 runs, N1, 2a, 3.x, W-28, merges, review fixes | Sonnet (lane) | about 190 |
| W-13, W-01, O-R-07, O-P-03 (helper A) | Sonnet | 7 |
| items C, D, E, F, G (helper B) | Sonnet | 14 |
| Opus reviews of N1 and of push 2 | Opus | 7 and 10 |

SAFE TO CLOSE: not yet (second gate pending; plan-watch cost and N8 not done)
