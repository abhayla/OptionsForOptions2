---
work_item: W-213
requirement: REQ-169
ac: AC-1
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "b49d4eceeef7"
commands: "git rev-parse HEAD (1bde4efc); read routes/system_playbooks.py, routes/playbooks.py:188-198, routes/settings.py:66, SystemPlaybookAdmin.vue, AdjustmentsPage.vue:39-46,311; cd frontend && npx vitest run tests/system-playbook-admin.test.js"
---
All three system-playbook routes sit behind require_admin (system_playbooks.py:35); Save calls the same precheck as a user save (playbooks.py:198); the admin component renders only under viewer.isAdmin; Test (/playbooks/test) works on system playbooks and writes nothing. vitest 6/6 incl. 'admin flag off, no controls and no admin read'. Attack: a non-admin - require_admin is a passthrough until sign-in, as REQ-167 AC-3 allows.

Test before Save is offered, not forced (matches the AC). DB proof owed: tests_app/test_system_playbook_versions.py::test_a_non_admin_is_refused_on_every_route_and_nothing_is_written, ::test_an_invalid_body_is_refused_with_the_same_answer_as_the_user_editor. Real role check owed when sign-in lands.

Recorded by the orchestrator from the verifier's returned block.
