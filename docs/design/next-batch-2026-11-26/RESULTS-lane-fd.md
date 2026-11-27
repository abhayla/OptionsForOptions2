# Lane FD round 2: backend totals, connection holds, plan acceptance

STATUS: B1 committed (gate running; push after TOTAL PASS). B3 found already done. B2 and B5 not done; B4 handed off below. Updated at each push.

Spec basis: ADR-330 (62), (45), (41), (58); ADR-252 addendum; ADR-250; ADR-008. Paper only.

## B1 money total + connection hold

| Item | State |
|---|---|
| ADR-330 (62) booked result in the header total | Already in this build: Lane L's change landed as d175ea0 and 8fe6fa9 (rebased copies of bb845bd7 and 36aa14a1). Cherry-picking bb845bd7 gives an empty diff (conflicts were comment line wraps only; resolved to the build's side). Nothing to bring. Frontend and RESULTS files of that commit were not taken. |
| Core proof | `tests_app/test_paper_totals.py` + `test_paper_totals_lines.py` against local PostgreSQL 16: Passed in cloud, 33 passed. |
| place_paper_orders hold (paper.py) | Fixed. Passed in cloud: `tests_app/test_place_orders_pool_r2_fd.py`, 2 passed (the first-fill test failed red first: `entry_facts` ran with a transaction open; now released). RCA: the route released before the exit-price read, but `paper_store.tracked_ids` re-checked a connection out and `entry_facts` (entry ATM IV, a REST read) waited holding it. Class: a read between two market waits re-checks out the connection; each wait needs its own release. |
| Real path | The real first fill (`execution_return._return`) keeps its connection on purpose (strategy row lock, noted in tests/test_pool_release_before_market_wait.py). Its `_record_entry_facts` call also waits on the broker while holding it: GAP per ADR-330 (58), not changed. Listed for the owner. |

Order path: every refusal and sentence unchanged.

## B3 read-path holds: already done in this build

| Path | Evidence |
|---|---|
| adjustment_history.py:243 | releases before `market_snapshot`; test_adjustment_history.py::test_no_database_connection_is_held_while_the_market_snapshot_runs passes |
| routes/playbooks.py:520 (test_playbook) | releases before the gathered reads; tests_app/test_playbook_test_pool.py passes |
| routes/adjustment.py:614, 655, 668 (line 809 is the definition of `release_connection`) | tests_app/test_d36_adjustment_counts.py after_approaches / after_check no-connection tests pass |
| Structural | tests/test_pool_release_before_market_wait.py passes (GUARDED_COUNT 11, empty allowlist) |

I wrote no B3 code, so no new B3 test.

Failures also present on the UNMODIFIED build (the same 4 fail in a clean worktree of 16c536f0, so not from this lane; deferred): test_d36_adjustment_counts::test_approaches_counts_and_reply and ::test_check_counts_and_reply (expect strategy_id 1, get 123: they assume a fresh database, mine had earlier runs); test_pool_not_held_across_market_wait plan-watch x2 (REST reader not reached; cause not found).

## B2 plan acceptance (0058 to 0060): NOT DONE in this run
Read only. Facts for the next run: origin/feat/0058-plan-acceptance-1127 changes playbook_store.py, routes/adjustment_plan.py, openapi.json, the 0058 migration and tests, AND four frontend files (AdjustPlanSheet.vue, adjustPlan.js, adjust-plan.test.js, plan-accept-signal.test.js). The backend needs the sheet to send `accept: true` on "Use playbook as is" or a picked playbook, or those PUTs no longer stamp. That frontend part belongs to the frontend lanes: see "For the owner lane".

## B4 fired-exit wording: found, not changed
The sentence is `stop_fired_at` / `stop_fired_on` ("{line}; reached at {time} IST") in backend/ofo/errors/explanations.py (Lane FC's file), built in routes/adjustment_check.py `_reached`. It claims a "reached" time but the stored time is `paper_triggers.fired_at = clock_timestamp()` at the claim, when the monitor processed the tick, not the crossing tick. paper_monitor.py and plan_watch.py carry no time. Decided for the owner (pending owner read): "{line}; seen by the check at {time} IST" and "{line}; seen by the check on {date} at {time} IST". Not edited (outside this lane's files).

## B5 served field: not started

## Decided for the owner
- B1 cherry-pick skipped because identical content is already in the build (ADR-330 (62)).
- Real-path first-fill hold left as is (row lock; ADR-330 (58) gap listed).

## For the owner lane
- Frontend part of 0058 (accept flag) from f963ab6c: adjustPlan.js asIsBody/saveBody/fetchLevels and AdjustPlanSheet.vue.
- explanations.py: the two sentences above (B4).

## PC steps
Market closed: none for B1. Live: none.

NOT SAFE TO CLOSE: B2 and B5 remain.
