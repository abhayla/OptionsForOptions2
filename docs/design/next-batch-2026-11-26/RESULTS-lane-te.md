STATUS 03:40 | items 1-42: all PASS on build 70ee16ac (weekend-1127 + conflicts-1127) | full tests_app run: in progress | next push on full-run result | blocker: none

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

## Full tests_app run
(see the last section, filled when the run ends)

## Defects found
1. Test isolation (class, not product): `tests_app` files leave rows behind (the catalogue refusal "would drop 750 of 750 live NIFTY contracts", an
   extra `lapsed` alert beside the expected `open`). Run in sequence on one database they fail; each alone on a clean copy they pass.
   Failing test on a dirty database: `tests_app/test_last_leg_closes_alerts.py` (`['lapsed','open'] == ['open']`). For a fix lane: clean up or use
   a per-file schema. No product code defect found.

## Not proven by the named test (for Lane TA or TB)
1. I-51: a server test that the three leg-stop lines are short and carry "theoretical worst case" wording (`tests_app/test_leg_stop_risk.py` and
   `backend/ofo/errors/explanations.py` mention "worst case" and may already cover it; not in this lane's named files).
2. I-125: a test asserting the 10 s re-read (`REBUILD_SECONDS`) itself, not a 15 s or 20 s allowance.

## For the owner lane
- `frontend/tests/paper-exit-warning.test.js` line 4: the header still says "Confirm is never locked"; update to the hotfix 27 Nov rule.

## Decided for the owner
- The full run excludes the `full_chain` marker (migration down-and-back replays; nightly only, per `pytest-app.ini`).
- Each named `tests_app` file was run on its own clean database copy (see How it was run).

## To file as deferred issues
- Defect 1 (test isolation across files).

## Pending owner read (new on-screen sentences)
None; no product text was added.

## Tasks
| task | model | minutes |
|---|---|---|
| set-up, 42 named runs, READ items | Sonnet | about 30 |
