---
work_item: W-205
requirement: REQ-158
ac: AC-5
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "717159ac82cd"
commands: "read adjustment_check.py:135-143"
---
Not verified in budget. The precedence holds in resolve() (plan, then active, then system: adjustment_check.py:136-143). Not read: accept_plan's copy and migration 0031's FK on strategy_adjustment_plans.playbook_id, so 'deleting a playbook leaves the plan' is unproven here (the REQ-161 AC-3 verifier read that a delete sets playbook_id NULL and keeps the body).

DB proof owed: tests_app/test_playbook_store.py::test_a_plan_keeps_its_body_byte_identical_when_its_playbook_is_edited_then_deleted.

Recorded by the orchestrator from the verifier's returned block.
