STATUS 06:45 | items 1-42: all PASS on build 70ee16ac | full tests_app (fresh DB, per-file clones): 27 failed, 8090 passed, 5 skipped, 3 xfailed, 23 deselected, 67 min, all 27 reproduce file by file | gate TOTAL PASS on the first push (jobs 1) | next push: this file | blocker: none

# Lane TE results (28 Nov 2026; branch test/r2-named-green-1128 from origin/integration/weekend-1127 + origin/integration/conflicts-1127)

Paper only; no broker connection; market closed. Highest status claimed: tests green on the build, nothing fixed.

## How it was run
- PostgreSQL 16 (`pg_ctlcluster 16 main start`), roles as in `.github/workflows/app-tests.yml`, migrated to 0059 (head).
- Each `tests_app` file ran alone, on its own copy of a freshly migrated database (a template database cloned before each file).
  Reason: files run one after another on one database leave rows behind (first try: `test_last_leg_closes_alerts` 2 failed,
  `test_paper_order_lots_limit` 19 failed, `test_paper_settlement` 16 failed, `test_close_freeze_routes` 4 failed,
  `test_paper_server_exit_price` 4 failed, `test_clock_ahead_records` 1 failed; the same files all passed on a clean copy).
  This is the same class Lane Z saw (see "Defects found" 1).
- Frontend: `npm ci` then `npx vitest run tests/<file>.test.js` per file. Domain tests: `python -m pytest tests/...`.
- Proof first: `tests_app/test_last_leg_closes_alerts.py` (I-05) on PostgreSQL: **2 passed** (7.55 s), before the rest.

## READ items (what the assertion proves)
- **I-15** `fe/paper-exit-warning.test.js` line 75-88: proves it. While the read is held pending it asserts the checking line shows and
  `paper-confirm-button` has `disabled` defined (line 82), then after the answer Confirm is enabled (line 87). Note: the file header
  (line 4) still says "Confirm is never locked"; stale comment, the assertion is the newer rule (hotfix 27 Nov).
- **I-37** `ta/test_paper_order_lots_limit.py`: both cases are present. 101 lots on an empty leg refused at 100 (line 161, also 215, 236);
  60 held + 50 more refused at 100 (line 128, text "60 held, 50 added"); 100 total accepted and 101 refused (line 142); freeze-limit refusals per leg
  (lines 49, 70, 194, 272). `ta/test_lots_cap_guard.py` proves every route with a lots field reaches the shared check. Proves the item.
- **I-51** `fe/paper-stops-leg-risk-w2b.test.js`: only half. It proves the screen prints the server's three lines, each on its own line, in order,
  with no figure of its own, and falls back to one sentence if the list is not three non-empty texts (line 85-101). The "theoretical worst case"
  wording is a fixture (line 44, "worst case: NIFTY at zero"), so this file does not prove the server writes three SHORT lines with that wording.
  See "Not proven by the named test" 1.
- **I-125** `ta/test_plan_stop_worker_chain.py`: only partly. Test k (line 256) asserts the alert row within `SAVE_TO_ALERT_SECONDS = 15` of the save
  with the worker not told of the change; tests b and h sleep `RELOAD_SECONDS = 20` (line 30). Nothing asserts 10 s. The product constant is
  `REBUILD_SECONDS = 10` (`backend/ofo_app/background.py:183`). So "re-read within one cycle (about 10 s plus a check)" is proven at 15 s, not "10 s".
  See "Not proven by the named test" 2.

## Per item (pass counts per file)
| # | Item | Result | Files and pass counts |
|---|---|---|---|
| 1 | I-01 | PASS | t/adjustment/test_stop_gaps_1127.py 36; test_rupee_stop_immediate.py 13; test_alert_gate_cap_exempt.py 14; ta/test_plan_save_1127.py 10 |
| 2 | I-04 | PASS | fe/alerts-exit-door-w2b 8 |
| 3 | I-05 | PASS | ta/test_last_leg_closes_alerts 2 |
| 4 | I-07 | PASS | ta/test_clock_ahead_records 2 |
| 5 | I-11 | PASS | fe/exit-not-live-good-read 19 |
| 6 | I-12 | PASS | fe/exit-end-sentence 4; ta/test_paper_server_exit_price 4 |
| 7 | I-13 | PASS | fe/exit-dialog-page-close 19 |
| 8 | I-15 | PASS | fe/paper-exit-warning 9 (assertion read: proves) |
| 9 | I-19 | PASS | fe/exit-end-sentence 4 |
| 10 | I-22 | PASS | fe/plan-save-outcome 17 |
| 11 | I-23 | PASS | ta/test_plan_save_1127 10; ta/test_plan_read_2_1127 12 |
| 12 | I-31 | PASS | fe/price-notice-adr330-56 7; fe/price-scope-adr330-56 5 |
| 13 | I-33 | PASS | t/marketdata/test_close_freeze 24; ta/test_close_freeze_routes 4; ta/test_picker_closed_freeze 1 |
| 14 | I-34 | PASS | ta/test_closed_label_route 5 |
| 15 | I-35 | PASS | ta/test_paper_unpriced_names 5; fe/unpriced-legs-adr311 10 |
| 16 | I-36 | PASS | fe/exit-market-closed-adr330-60 7; ta/test_exit_market_adr330_60 5; fe/paper-add-not-live 4 |
| 17 | I-37 | PASS | ta/test_paper_order_lots_limit 19; ta/test_lots_cap_guard 4 (101-lot and 60+50 cases present) |
| 18 | I-38 | PASS | fe/paper-totals-one-set 7; ta/test_paper_totals_lines 11; fe/home-figures-d56 18 |
| 19 | I-42 | PASS | ta/test_paper_totals_lines 11 |
| 20 | I-45 | PASS | fe/paper-totals-one-set 7; fe/home-figures-d56 18 |
| 21 | I-46 | PASS | ta/test_paper_settlement 29; t/engine/test_expiry_day_d08_d12 10; ta/test_expiry_day_paper_chain_d12 2 |
| 22 | I-51 | PASS (half proven, see READ) | fe/paper-stops-leg-risk-w2b 15 |
| 23 | I-52 | PASS | fe/builder-closed-plan-final-57 4; fe/builder-completed-n48 1 |
| 24 | I-53 | PASS | fe/plan-door-positions-54 8 |
| 25 | I-54 | PASS | fe/adjust-acted-handoff 11 |
| 26 | I-56 | PASS | fe/paper-move-stop-offer-774 7; fe/leg-expiry-door 10; ta/test_leg_edit_expiry_route 5 |
| 27 | I-73 | PASS | ta/test_strategy_duplicate_leg_refusal 4 |
| 28 | I-77 | PASS | ta/test_plan_sheet_refusal_labels 10 |
| 29 | I-84 | PASS | fe/unsaved-reload-note-adr330 3; fe/leave-builder-adr329 21 |
| 30 | I-87 | PASS | fe/one-date-formatter-d57 7; fe/rename-paper-d65 6 |
| 31 | I-89 | PASS | ta/test_history_delete_entries 11; ta/test_strategy_bulk_delete 11 |
| 32 | I-99 | PASS | ta/test_execute_plan_typed_entry 14; fe/paper-add-not-live 4 |
| 33 | I-101 | PASS | fe/exit-all-staged-adr330-59 7 |
| 34 | I-114 | PASS | ta/test_paper_entry_price_zero 6 |
| 35 | I-115 | PASS | ta/test_picker_closed_freeze 1; fe/leg-picker-centre-closed 2 |
| 36 | I-117 | PASS | fe/position-kind-adr330-64 4 |
| 37 | I-118 | PASS | fe/monitoring-state-lane-y 6; ta/test_monitoring_status_route 7; ta/test_monitoring_state 10 |
| 38 | I-119 | PASS | ta/test_plan_read_2_1127 12 |
| 39 | I-120 | PASS | ta/test_order_door_entry_facts_confirmed 7 |
| 40 | I-123 | PASS | ta/test_plan_read_2_1127 12; ta/test_monitoring_state 10 |
| 41 | I-124 | PASS | ta/test_plan_read_2_1127 12 |
| 42 | I-125 | PASS (partly proven, see READ) | ta/test_plan_stop_worker_chain 12 (457 s); ta/test_plan_rupee_worker 1 |

I did not check, per item, that each test name matches the item's sentence beyond the four READ items; "PASS" means the named file ran green.

## Gate (first push, docs-only commit)
`prepush.py` did not end TOTAL PASS; none of the failures touch this commit (one RESULTS file):
- `ci_checks`: `git merge-base origin/main HEAD` failed because the container clone was shallow; fixed with `git fetch --unshallow` (not yet re-run).
- `app_tests`: "git diff failed (rc 128)", same shallow cause.
- `frontend_unit`: 2 failures that are timeouts under load (the full `tests_app` run was using the machine): `exit-all`/ADR-329 (1) C2 same-action clash test (15.5 s) and N-07 guard scan (17.6 s). Re-run when the full run ends.
Result: not pushed at that point (the push hook refuses without a passing gate; I did not set `PREPUSH_GATE_ALLOW`). Two more default runs failed on one test, `paper-leg-readers-guard` "N-07 guard" (16.7 s and 27.2 s under four parallel jobs; 5.2 s alone; testTimeout 15 s). With `PREPUSH_JOBS=1` the gate ended **TOTAL PASS** (2775 s, 04:17 to 05:03) and the first push went out at 05:03, about 56 minutes after the 60-minute target. Finding: on this 4-core container the default gate flakes on that one test; use `PREPUSH_JOBS=1`.

## Full tests_app run
Command: `GITHUB_ACTIONS=true python -m pytest -c pytest-app.ini tests_app -q -m "not full_chain"` on a freshly dropped, recreated, granted and migrated
database (head 0059), nothing else running. `GITHUB_ACTIONS=true` switches on the suite's own per-file database clone (`tests_app/conftest.py`
`should_clone`); without it (or a `db_run_fresh` name) files share one database and fail in sequence (first full try: failures from the 11th test on,
then a crawl on a leaked advisory lock held by an idle-in-transaction session, which is the hang Lane Z saw; that run was stopped at 23 %).
**Result: 27 failed, 8090 passed, 5 skipped, 3 xfailed, 23 deselected (`full_chain`), 4041 s (1:07:21).** None of the 27 is in a file named for the 42 items.
Each of the 12 files failed the same way when run alone on its own clone (re-run logs kept locally), so none is an order effect.

| file | failed | what it said (first line) | likely class |
|---|---|---|---|
| test_adjustment_history_why.py | 1 | `test_an_adjustment_from_a_suggestion_names_its_rule...` line 136: reply is `STRATEGY_VALIDATION_505` ("No order was stored; a partial exit counts as an adjustment") where the test expects acceptance | product or test out of step |
| test_alert_routes.py | 2 | lines 46 and 86: answer key set differs from the expected set | test out of step with a new field |
| test_d38_page_counts.py | 1 | line 94: "plan: the reply changed" | test out of step |
| test_egress_gate_doors.py | 3 | line 55: `KiteExchangeError('kite_unavailable')` instead of the egress-gate refusal | container network (proxy), likely environment |
| test_kite_broker_reader.py | 1 | `HTTPError 400 Bad Request` from urllib (a real outbound call went through the proxy) | container network, environment |
| test_execution_return.py | 2 | `test_real_first_fill_stores_entry_facts_once` (2 cases) line 582: `INTERNAL_SYSTEM_002` unhandled error on POST /strategies/1/execution/return | **product, near I-120**; see Defects 2 |
| test_migration_0059_last_close.py | 4 | line 76: SQLSTATE `22000` where the test expects `23514` (check violation) | Postgres 16 minor version or trigger raise; check |
| test_pinned_clock.py | 1 | line 140: fixture offered on the real clock (a `default_exp...` dict differs from the pinned one) | clock: today is Sat 28 Nov, market closed |
| test_pool_not_held_across_market_wait.py | 2 | line 109: "the REST reader was not reached: the measurement proves nothing" | timing or market closed |
| test_risk_exit_not_gated.py | 1 | line 95: `[] == [(1, 'open')]` (no record opened) | clock: market closed |
| test_route_latency_budget.py | 4 | statement counts over the ceiling: plan-watch 24 (ceiling 23), adjustment-plan 19 (ceiling 18), adjustment-check, batch of one row 24 | **product**: one extra query per route; see Defects 3 |
| test_slow_price_source_live_day.py | 5 | `asyncio TimeoutError`, and `XPASS(strict)` on three xfail markers ("a paper read holds its pooled conn", "plan-watch waits out the whole stall") | tests expect the old behaviour; the xfails now pass, so the markers must go |

I did not diagnose root causes beyond this table (budget); the "likely class" column is a guess [Guessing] except the quoted lines.

## Defects found
1. Running `tests_app` on one shared database (the "run the whole suite" way this brief and `db_run.py` imply) fails from the 11th test on and then
   crawls on a leaked advisory lock; it needs the per-file clone (`GITHUB_ACTIONS=true` or a `db_run_fresh` database name). Repro on a fresh
   database: `test_acted_on_at_place.py` then `test_actionable_alerts.py` (catalogue refusal "would drop 750 of 750 live NIFTY contracts"); the same
   files alone pass (36 passed and 2 passed). For the owner lane: say in the runbook that a manual full run must set `GITHUB_ACTIONS=true`
   (or use `db_run_fresh`). No product code defect.
2. `tests_app/test_execution_return.py::test_real_first_fill_stores_entry_facts_once` (2 cases) fails on this build with an unhandled error
   (`INTERNAL_SYSTEM_002`) on POST `/strategies/1/execution/return`; the named I-120 file `test_order_door_entry_facts_confirmed.py` (7) passes, so the
   first-fill-on-the-return-route path is the one that breaks. Failing test is the one named; needs a fix lane to read the traceback.
3. `tests_app/test_route_latency_budget.py`: one statement over the ceiling on plan-watch (24 vs 23), adjustment-plan (19 vs 18),
   adjustment-check and the batch of one row (24): a query was added to those routes after the ceilings were set (finding class: statement-count ceiling).
4. `tests_app/test_slow_price_source_live_day.py`: three `xfail(strict)` markers now XPASS, so the product got better than the test says; markers
   to remove. Two other cases time out (real failure or timing, not diagnosed).

## Not proven by the named test (for Lane TA or TB)
1. I-51: a server test that the three leg-stop lines are short and carry "theoretical worst case" wording (`tests_app/test_leg_stop_risk.py` and
   `backend/ofo/errors/explanations.py` mention "worst case" and may already cover it; not in this lane's named files).
2. I-125: a test asserting the 10 s re-read (`REBUILD_SECONDS`) itself, not a 15 s or 20 s allowance.

## For the owner lane
- `frontend/tests/paper-exit-warning.test.js` line 4: the header still says "Confirm is never locked"; update to the hotfix 27 Nov rule.

## Decided for the owner
- The full run set `GITHUB_ACTIONS=true` (the suite's own switch for one database copy per file) and excludes the `full_chain` marker (migration down-and-back replays; nightly only, per `pytest-app.ini`).
- Each named `tests_app` file was run on its own clean database copy (see How it was run).

## To file as deferred issues
- Defect 1 (runbook: full run needs `GITHUB_ACTIONS=true`), 2 (execution/return first fill), 3 (latency ceilings), 4 (slow price xfails); the failures in the table that are not listed as a defect.

## Pending owner read (new on-screen sentences)
None; no product text was added.

## Tasks
| task | model | minutes |
|---|---|---|
| set-up, 42 named runs, READ items | Sonnet | about 30 |
| gate runs (4) | Sonnet | about 90 |
| full tests_app run, triage of 27 | Sonnet | about 100 |


Budget: 240 min wall-clock; used about 215 min plus the final gate run.
