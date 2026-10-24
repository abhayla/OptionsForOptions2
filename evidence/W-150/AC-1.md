---
work_item: W-150
ac: AC-1
requirement: REQ-034
ac_fp: "7f73f42ff452"
result: pass
verified_by: "independent verifiers (Opus row 22 check + round 2 on f5ab7f1e; Sonnet AC-1/5/7 re-check on bf4823e7; Sonnet 22b check on e928a3af)"
builder: "builders (Opus: row 22 d0a6049f, ATM-IV fix f5ab7f1e; Sonnet: 22b e928a3af)"
date: '2026-10-24'
commands: "npx vitest run tests/outcome-view.test.js tests/advanced-details-health.test.js tests/strategy-table.test.js tests/builder-lines.test.js tests/strategy-live.test.js (69 passed); npm run lint (0 errors); python -m pytest -q -p no:cacheprovider -c pytest-app.ini <72 select_app_tests files> (1582 passed, 299 skipped) on e928a3af"
---

AC: AC-1
result: pass
commands: npx vitest run tests/outcome-view.test.js tests/advanced-details-health.test.js tests/strategy-table.test.js tests/builder-lines.test.js tests/strategy-live.test.js (69 passed); npm run lint (0 errors); python -m pytest -q -p no:cacheprovider -c pytest-app.ini <72 select_app_tests files> (1582 passed, 299 skipped) on e928a3af
observed: The mounted StrategyBuilderPage shows the plain sentences, max profit/loss, breakevens, the payoff chart, the scenario table and the margin line with no click; e2e strategy-table.spec.ts asserts the figures on /strategy/builder (green in CI run 40063948683 before 22b).
attack: Capability off: margin state HIDDEN with the documented reason and no figure; an answer without leg_quotes has no details block and the rest still shows; adding open to the details fails 3 tests.

Recorded by the orchestrator from the verifier's returned block.
