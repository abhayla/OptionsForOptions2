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
