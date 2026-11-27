# RESULTS Lane TB: frontend unit tests for 10 screen items

STATUS: IN PROGRESS (push 1: items 1, 2, 3, 4, 6, 7 proven; 5, 8, 9, 10 to do). Branch test/r2-frontend-1128 from origin/integration/weekend-1127; the first-command merge of origin/integration/conflicts-1127 brought Lane J3's files (RESULTS-lane-j3.md, tests_app/test_worker_j3.py and 4 more). Paper only, no broker.

Notes on the brief
- `.claude/skills/lanes/SKILL.md` does not exist in this checkout (only deliver, intake, options-math-review). Worked from the lane brief alone.
- `docs/process/test-plan-weekend-2026-11-28.md` exists only on origin/docs/test-plan-weekend-1127; the ids I-xx are not defined there, so each item follows the queue text.

| # | Item | Result | Test (file > name) |
|---|------|--------|--------------------|
| 1 | I-40 | PASS (2 tests) | tests/my-strategies-bulk.r2-1128.test.js > "I-40: ..." |
| 2 | I-60 | PASS (3 tests) | tests/alerts-history-d22.r2-1128.test.js > "I-60 ..." |
| 3 | I-65 | PASS (2 tests) | tests/paper-stops.r2-1128.test.js > "I-65 ..." |
| 4 | I-69 | PASS (1 test) | tests/my-strategies.r2-1128.test.js > "I-69 ..." |
| 5 | I-74 | not started | |
| 6 | I-76 | PASS (3 tests) + 1 `it.fails` for a defect (below) | tests/paper-alerts.r2-1128.test.js > "I-76 ..." |
| 7 | I-80 | PASS (3 tests). The DB half tests_app/test_strategy_bulk_delete.py is NOT covered (not this lane) | tests/my-strategies-bulk.r2-1128.test.js > "I-80 ..." |
| 8 | I-83 | not started | |
| 9 | I-94 | not started | |
| 10 | I-98 | not started | |

Core (I-40), read back: 17 rows seeded, the bulk bar reads "Select all 17 shown", ticking all gives "Delete selected (17)"; with one row that cannot be ticked it reads "Select all 16 of the 17 shown".

## Gate result, push 1
- `npm run test:run` (whole frontend): 317 files, 3758 tests, all passed. My five files: 15 tests passed. `eslint` on my files: clean.
- `python scripts/orchestrator/prepush.py`: frontend_lint PASS, frontend_build PASS, coverage PASS, alembic_guard PASS. FAIL for container reasons, none touched by this lane (it adds only frontend test files and this note): ruff_ratchet (installed ruff 0.17.6 differs from the pinned one; rules PLR0917, RUF036, RUF100, SIM102 "rose" in backend code I did not touch), app_tests and preflight-collect (`sqlalchemy` not installed in this container; `git diff` against main fails), and the steps that stop with them. So the marker was not written and the push used `PREPUSH_GATE_ALLOW` with that reason.

## Decided for the owner
- I-40: the product label is "Select all N shown" (N = rows listed); the brief's "Select all 17" is asserted as that full sentence.
- I-60: the partial-failure message is the shared catalogue sentence "The page could not get an answer from the server." under the heading of the half that failed; the other half keeps its rows. Asserted whole (toBe), so a cut-off text fails.
- I-80: the "30 second hold" is the served Undo wait (mocked 30 000 ms): the pop-up Undo is present at 29 s and gone at 30 s; the result-line Undo and Dismiss have no timer and stay until used.

## Defects found
- Alerts > History shows "No stops or expiry settlements yet." while both reads are still pending (AlertsPage.vue: the `alerts-empty` EmptyState v-if does not check `alertHistory.loaded` / `paperRecords.loaded`; Active does). Test: tests/paper-alerts.r2-1128.test.js > "I-76 (same class) ... History ..." is an `it.fails` (change to `it` once fixed).

## For the owner lane
- AlertsPage.vue: add the loaded checks to the History empty state (above).
