---
work_item: W-208
requirement: REQ-161
ac: AC-1
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "a186a8f1756b"
commands: "git rev-parse HEAD (1bde4efc); read backend/ofo_app/routes/adjustment_plan.py, playbook_store.py, SaveDraftBar.vue, AdjustPlanSheet.vue; cd frontend && npx vitest run tests/adjust-plan.test.js"
---
Code path, not label: adjustment_plan.py:270 active = store.active_for(...), :272 chosen = active, :281 prefill from chosen.body; active_for (playbook_store.py:510-518) returns the user's active row, else the system row. The sheet holds playbook, target, stop, max, time and Customise triggers (AdjustPlanSheet.vue:17-37); SaveDraftBar.vue:359 opens it only after addToPaper succeeds. vitest 13/13 incl. 'a failed placement never opens the sheet'.

Server prefill not mocked in vitest. DB proof owed: tests_app/test_adjustment_plan.py::test_get_without_a_plan_prefills_from_the_active_system_playbook_and_pick_refills, ::test_core_use_as_is_copies_the_active_playbook_and_a_later_save_in_place_leaves_the_plan_identical.

Recorded by the orchestrator from the verifier's returned block.
