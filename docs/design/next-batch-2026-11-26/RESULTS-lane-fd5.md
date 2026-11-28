STATUS 13:05 | N1 built (sha in the push message), item 1 done | next: Opus review of N1, then item 2 | blocker: none

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

SAFE TO CLOSE: not yet (queue items 2 to 4 and the coordinator's round 1 items follow).
