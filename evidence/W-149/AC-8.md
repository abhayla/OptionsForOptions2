---
work_item: W-149
ac: AC-8
requirement: REQ-077
ac_fp: "aba76c53a554"
result: pass
verified_by: "independent verifiers (Opus part checks 21m/21b/21a/21d with round 2; Sonnet 21c check + round 2; Opus CI-fix check + round 2; Opus row 21 closing check on 9730cda2)"
builder: "builders (Opus: 21m 8a3bf0d2, 21b 8f5dc56e, 21a c851c84d, 21d 6d4ae53f; Sonnet: 21c f1a5e938 + fix 264576bb, CI fix 6bac88cf..ab38cd8d)"
date: '2026-10-24'
commands: "app run incl. tests_app/test_execute_plan_typed_entry.py and test_execute_route.py; mutant M1 execute_plan.py:162 limit from planned_entry; M2 routes/execute.py:501 planned_price None; vitest tests/execute-screen.test.js"
---

AC: AC-8
result: pass
commands: app run incl. tests_app/test_execute_plan_typed_entry.py and test_execute_route.py; mutant M1 execute_plan.py:162 limit from planned_entry; M2 routes/execute.py:501 planned_price None; vitest tests/execute-screen.test.js
observed: execute_plan.py:149-162: planned_entry is only the slippage reference passed to executable_limit(depth, ...); the limit is result.limit from the walked depth. BasketOrderOut.planned_price (routes/execute.py:119, :488-501); ExecuteStrategyPage.vue shows 'Your planned price 81.30 - order limit 79.40'. Judged on today's code: ADR-095 tolerance is not wired; owner Q1 (docs/process/owner-questions-2026-10-25.md) decides how it will be.
attack: M1: 1 failed (test_ac8_typed_entry_30_percent_above_or_below_gives_the_same_limit_as_no_entry[Action.BUY]). M2: 1 failed, 5 passed. Thin depth, a band and a missing quote refuse whatever the typed price.

Recorded by the orchestrator from the verifier's returned block.
