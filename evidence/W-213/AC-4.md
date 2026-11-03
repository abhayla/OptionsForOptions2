---
work_item: W-213
requirement: REQ-169
ac: AC-4
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "d28e2b186af2"
commands: "read playbook_store.py:397-405,422-434,510-518,530-543; read adjustment_check.py:136-142; read tests_app/test_system_playbook_versions.py:76-111"
---
A system playbook is read through _current() (newest version) in get, list_for_type and active_for, so a strategy with no plan gets the new version at its next check (adjustment_check.py:141). A plan is a stored copy read first (:136-138); a user copy is a user row returned unchanged. Attack: a system save only inserts into system_playbook_versions, so copies and plans cannot change.

PASS rests on code reading. DB proof owed: tests_app/test_system_playbook_versions.py::test_core_proof_new_version_reaches_the_next_check_copies_and_plans_unchanged_restore_appends (IC T-06 50 -> 45; copy and plan stay 50).

Recorded by the orchestrator from the verifier's returned block.
