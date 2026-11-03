---
work_item: W-209
requirement: REQ-162
ac: AC-1
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "0f40e8f1a791"
commands: "cd frontend && npx vitest run tests/adjustment-opportunities.test.js; read backend/ofo_app/routes/adjustment_opportunities.py, backend/ofo_app/playbook_store.py (_INBOX), frontend/src/pages/AdjustmentOpportunitiesPage.vue"
---
vitest 19 passed. _INBOX joins strategies on user_ref (paper and imported real strategies both included; paper flagged by EXISTS on paper_orders); inbox_body groups by strategy and group id, newest first, with the strategy name and shown_at; the page shows Time and Strategy columns. Attack: another user's rows are excluded by the user_ref predicate.

DB proof owed: tests_app/test_adjustment_opportunities.py::test_adj02_worker_opens_three_records_the_screen_check_names_them_and_opens_none (read by name only).

Recorded by the orchestrator from the verifier's returned block.
