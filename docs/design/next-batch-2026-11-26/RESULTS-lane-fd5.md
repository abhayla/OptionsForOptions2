STATUS 12:10 | item 1: done (all files green alone on a fresh database; 1 test edited) | next push: item 2 | blocker: none

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

SAFE TO CLOSE: not yet (queue items 2 to 4 follow).
