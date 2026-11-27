STATUS 03:50 | item: I-02..I-58 proven (6 of 15) | next push 04:45 | blocker: none

# Lane TA: database tests for 15 backend items (28 Nov 2026)

Branch `test/r2-backend-1128`, from `origin/integration/weekend-1127` + `origin/integration/conflicts-1127` (merged first).
Database: PostgreSQL 16, roles as in `app-tests.yml`, migrated to 0059. Each file is run on a FRESH database copied from a
migrated template (the seeded tests commit the scenario library; the rolled-back tests need an empty catalogue, so the
two families cannot share one database: a note for the owner PC, not a defect).

## Items
| Item | State | Evidence |
|---|---|---|
| I-02 | PASS | `tests_app/test_plan_rupee_worsen_recover_r2_1128.py` 1 passed (twice). Red proof: with the worse-reading rule switched off in memory the test fails (`value 400 != 650`). Worse updates the same open row, recovery keeps it open with "no longer true since", a loss past the line again clears the note, one row throughout. |
| I-03 | PASS | `tests_app/test_alert_continue_stop_r2_1128.py` 2 passed (percent stop and rupee stop): Continue clears the alert from Active, bell is exactly one lower, History has answer `continue`, `paper_orders` unchanged. |
| I-39 | PASS (API half) | `tests_app/test_completed_header_count_r2_1128.py` 1 passed: 15 closed + 1 draft + 1 hidden closed -> `GET /strategies` returns exactly the 15 completed ids, once each. The header's number is not computed by the server (no count field in `StrategyListOut`); it is the frontend's. See "For the owner lane". |
| I-44 | PASS | `tests_app/test_paper_totals_settled_unpriced_r2_1128.py` 5 passed: a settled trade adds booked only; an unpriced one makes unbooked and total absent with its reason; left out ones are counted. |
| I-55 | PASS | `tests_app/test_side_closed_no_plan_r2_1128.py` 2 passed: a trade with no plan is not listed by the worker's lister, so no `side_closed` alert; control with plan is listed. |
| I-58 | PASS | `tests_app/test_alert_reason_words_r2_1128.py` 12 passed: each of the six actionable kinds, with and without figures: Active text is never the trade name, names its rule kind in words, carries the figures when present, and History repeats the same words. (The fallback `_rule_in_words` in `routes/alerts.py` already exists; no defect.) |
| I-59 | PASS | `tests_app/test_plan_time_exit_one_alert_r2_1128.py` 1 passed (worker as its own process, PATH-93, whole system rule list on, time exit 11:43): ONE new alert, kind `plan_time_exit`, rule `T-10b`, Active text "Time exit reached". The defect (two alerts, neither named) is not reproduced on this build. |
| I-63 | PASS (side pinned); Opus review pending | `tests_app/test_stop_side_sold_leg_r2_1128.py` 9 passed. **Which side: for a SOLD leg the loss stop sits ABOVE the leg's price** (the SELL 22800 CE at 39.15 takes "above 135.00": armed `above`, fires at or above 135.00, never at 134.99; a level below the price, e.g. "below 135.00" with the price at 39.15, is refused "straight away ... use Exit"). So a stop reading "above 135.00" while the price is lower is the CORRECT side, not P0. Sentence for it: "If this stop fires, max loss becomes Rs 7,072.00 (now Rs 11,297.00)." (see Observation 1). `frontend/tests/two-stops-words.test.js` is Lane TB territory. |
| I-64 | PASS | `tests_app/test_plan_watch_draft_r2_1128.py` 3 passed: a just-saved draft is 200 `no_plan` with the catalogue sentence, no lines, never "not found"; the batch row is `ok`; another user's, a hidden and an unknown id stay 404. |
| I-81 | PASS | `tests_app/test_adjustment_history_other_user_r2_1128.py` 2 passed: another user's strategy is 404, the body is identical to a missing id's, carries no figure, and the raw counts (orders, suggestions, strategies, revisions) are the same after the read; a hidden own strategy is 404. |
| I-82 | PASS (order decided) | `tests_app/test_adjustment_opportunities_order_r2_1128.py` 1 passed, `tests/adjustment/test_popup_order_r2_1128.py` 6 passed. Decided: Active and the ideas list newest first by raise time; a lapsed idea leaves Active and keeps its raise-time place in the ideas list; History by end time, newest first (stop-out notes and lapsed rows). Pop-ups: a stop-out crossed at 3 minutes waits with a rule true at entry and both fall due at entry + 5. |
| I-90 | PASS | `tests_app/test_deleted_trade_plan_hidden_r2_1128.py` 7 passed: plan, rules, levels, plan-watch, check and history links of a deleted trade are 404 (body equal to a missing id's) and 200 again after Undo; its alert leaves Active and the bell, its ideas leave the list, its batch row is refused 404, answering its alert is 404. |
| I-105 | PASS (structural) | `tests/test_pool_release_playbooks_r2_1128.py` 2 passed: a transitive scan sees `playbooks._tested` reach the market through helpers and finds `release_connection(db)` before it; mutation (release line removed) is flagged. Runtime twin already exists (`tests_app/test_playbook_test_pool.py`). See Observation 2. |

## Gate
Push 1: `prepush.py`: ruff_ratchet PASS, coverage PASS, alembic_guard PASS; ci_checks 14 passed, 1 failed (`git merge-base origin/main HEAD`: this clone has no origin/main), frontend_lint/build/unit FAIL (no `frontend/node_modules`: environment, not the tests), app_tests FAIL (cannot select by `git diff`: same missing base). Not `TOTAL PASS` for environment reasons; my files pass ruff and their own DB runs.

## Decided for the owner
- Fresh database per test file (template copy, 0.4 s) because the seeded and rolled-back test families pollute each other on one database.

## Defects found
(none yet)

## For the owner lane
- I-39: `side_closed.raise_if_closed` itself has no plan check; the guard is the lister (tested). If another caller is added, it needs its own guard.
- I-39: the Completed header number is computed in the frontend; Lane TB should assert header count == rows shown there.

## To file as deferred issues
(none yet)

## Models
| task | model | minutes |
|---|---|---|
| items 1-5 | Sonnet | 12 |
