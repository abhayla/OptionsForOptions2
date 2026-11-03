---
work_item: W-208
requirement: REQ-161
ac: AC-3
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "e28dee4e00ff"
commands: "read playbook_store.py:530-543 accept_plan, :207-213 _UPSERT_PLAN; grep -rn strategy_adjustment_plans backend --include=*.py (insert/update/delete); read adjustment_check.py:135-143 resolve; read PlanEntry.vue, TrackingPanel.vue:52; read tests_app/test_adjustment_plan.py:178-229, tests_app/test_playbook_store.py:189-202"
---
accept_plan validates and writes the body as the plan's own JSONB copy; the upsert at :207 is the only write path; no code updates a plan from a playbook or settings change; resolve() reads the plan first; Edit reopens the sheet with PUT. Attack: no other writer to the plans table; a playbook delete sets playbook_id NULL and keeps the body.

A settings change leaving the plan alone holds because no settings path writes the plans table (no direct test). DB proof owed: tests_app/test_adjustment_plan.py::test_core_use_as_is_..., ::test_overrides_land_in_the_copy_only_and_an_edit_keeps_them, tests_app/test_playbook_store.py::test_a_plan_keeps_its_body_byte_identical_when_its_playbook_is_edited_then_deleted.

Recorded by the orchestrator from the verifier's returned block.
