---
work_item: W-205
requirement: REQ-158
ac: AC-5
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 4)"
date: 2026-11-04
ac_fp: "717159ac82cd"
commands: "read backend/ofo_app/adjustment_check.py:135-143; read backend/ofo_app/playbook_store.py:517-568; grep strategy_adjustment_plans backend (*.py); read backend/ofo_app/alembic/versions/0031_adjustment_playbooks.py:28-31,408-412; read tests_app/test_playbook_store.py:189-202, tests_app/test_adjustment_check.py:242-255"
---
resolve() returns the plan first, then active_for (user's active or system) (adjustment_check.py:136-143); accept_plan stores a copy via _UPSERT_PLAN (playbook_store.py:566), the only writer of strategy_adjustment_plans; save_in_place and delete never touch it; the FK is playbook_id ON DELETE SET NULL (0031:410), so deleting a playbook only nulls the pointer. Attack: edit, delete, then activate another playbook - the DB tests assert the body stays byte-identical and the source stays 'plan' (read, not run).

DB proof owed: tests_app/test_playbook_store.py::test_a_plan_keeps_its_body_byte_identical_when_its_playbook_is_edited_then_deleted, tests_app/test_adjustment_check.py plan-precedence test.

Recorded by the orchestrator from the verifier's returned block.
