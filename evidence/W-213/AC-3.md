---
work_item: W-213
requirement: REQ-169
ac: AC-3
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "0415769ab123"
commands: "read system_playbook_store.py:156-164; read SystemPlaybookAdmin.vue:17,55; read playbook_store.py:397-405; python -m pytest -q -p no:cacheprovider tests/adjustment/test_system_playbooks_seed.py (4 passed); vitest system-playbook-admin.test.js (6 pass)"
---
approve() inserts a new version with status 'approved' and the same numbers, refuses when already approved, needs a reason and base_version and writes an audit row; who/when/status are stored per version; a save cannot flip approval (store:138-139); _current() gives the newest version's status, so lists show Draft or approved and the admin panel offers Approve only on a draft. Attack: restoring a draft v1 after approval makes it Draft again (status copied) - consistent with 'earlier version becomes current'.

DB proof owed: tests_app/test_system_playbook_versions.py::test_approve_marks_a_draft_approved_as_a_new_version_shown_on_the_playbook, ::test_a_save_cannot_change_the_approval_state.

Recorded by the orchestrator from the verifier's returned block.
