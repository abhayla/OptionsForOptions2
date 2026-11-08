---
work_item: W-208
requirement: REQ-161
ac: AC-4
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "6e925627c406"
commands: "python -m pytest -q -p no:cacheprovider tests/adjustment/test_strategy_type.py; cd frontend && npx vitest run tests/adjust-plan.test.js; read adjustment_plan.py:268-269 and 327-328, backend/ofo/errors/templates.py:1295, adjustment_check.py:135-143"
---
pytest 9 passed: no type for a 3-leg condor, an off-grid strike or no legs. With no type, GET returns generic=true with 'No playbook matches this strategy's shape, so only the generic triggers and approaches apply.' and no prefill; POST/PUT give 409 before any write; the sheet shows that text with only Close. resolve gives source 'none', so the check uses generic triggers.

DB proof owed: tests_app/test_adjustment_plan.py::test_untyped_shape_is_generic_and_post_is_refused_with_the_same_text. Check route with source 'none' not exercised.

Recorded by the orchestrator from the verifier's returned block.
