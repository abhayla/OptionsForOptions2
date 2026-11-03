---
work_item: W-204
requirement: REQ-157
ac: AC-1
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "0cdd08ae935d"
commands: "cd frontend && npx vitest run tests/adjust-compare.test.js tests/adjust-controls.test.js"
---
Kind and side chips, credit/debit and capped/uncapped chips, and ranges for debit, max loss, POP (at least), charges and orders with the correct direction; judge() applies them and the page renders each. Tests :158, :174, :186, :209 passed. Attack: UNLIMITED max loss is dropped by a max-loss limit and kept out of the range span.

Recorded by the orchestrator from the verifier's returned block.
