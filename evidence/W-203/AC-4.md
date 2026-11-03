---
work_item: W-203
requirement: REQ-156
ac: AC-4
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "f2f82e1e4f11"
commands: "python -m pytest -q -p no:cacheprovider tests/adjustment/test_approach_compare.py; cd frontend && npx vitest run tests/adjust-compare.test.js"
---
Leads are (n, m) with m the rows that have a leader (compare.py:591-592); column_order puts A-36 first then catalogue order; test_ac4 reverses the input and the order holds. No best/better/winner/score/recommend in user text; the frontend test checks the rendered DOM for those words. The table sorts nowhere.

Recorded by the orchestrator from the verifier's returned block.
