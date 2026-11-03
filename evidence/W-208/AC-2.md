---
work_item: W-208
requirement: REQ-161
ac: AC-2
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "2e9bcbac14f1"
commands: "cd frontend && npx vitest run tests/adjust-plan.test.js; read AdjustPlanSheet.vue:97-120, frontend/src/lib/adjustPlan.js asIsBody/fetchPlan, adjustment_plan.py:263-286 and 321-342; PYTHONPATH=backend python -c (with_overrides/PlanIn probe)"
---
vitest 13/13. 'Use playbook as is' sends only {playbook_id} by POST and closes once; picking another playbook refetches GET ?playbook_id= and refills the form. A pick outside the type's list is a 422 (:274-276). Attack: the with_overrides probe leaves the source body unchanged; target 0, 100.5, max 11, time 24:00 and stop 'abc' are each refused naming the field.

DB proof owed: tests_app/test_adjustment_plan.py::test_invalid_values_a_wrong_type_and_put_without_a_plan_write_nothing.

Recorded by the orchestrator from the verifier's returned block.
