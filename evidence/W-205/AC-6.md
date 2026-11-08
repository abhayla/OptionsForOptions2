---
work_item: W-205
requirement: REQ-158
ac: AC-6
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "8f9e412101fe"
commands: "read backend/ofo_app/playbook_store.py:467-501; read backend/ofo_app/routes/playbooks.py:307-346; read frontend/src/pages/AdjustmentsPage.vue:37-44; read migration 0031 guard OF031"
---
save_in_place, rename and delete on a system playbook raise system_playbook_save_in_place (409) before any write; the DB guard OF031 blocks UPDATE/DELETE of system rows by the app role; 'Save as new playbook' creates the user's own; 'Save changes' and 'Delete' are hidden for system playbooks. Attack: a PUT on a system id hits the store refusal and the row is unchanged.

DB proof owed: tests_app/test_playbook_routes.py, tests_app/test_playbook_store.py.

Recorded by the orchestrator from the verifier's returned block.
