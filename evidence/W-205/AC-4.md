---
work_item: W-205
requirement: REQ-158
ac: AC-4
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "bb182d7fc839"
commands: "read backend/ofo_app/playbook_store.py:499-518; read migration 0031:397-406; read backend/ofo_app/routes/playbooks.py:349-368"
---
The active table's PRIMARY KEY (user_ref, strategy_type) allows one active row per type; make_active upserts it; the FK to playbooks is ON DELETE CASCADE, so deleting the active playbook removes the row and active_for falls back to the system playbook; delete() returns active_now_system with playbook_system_active_again. Attack: a second active row is blocked by the PK.

Exact message text not read. DB proof owed: tests_app/test_playbook_store.py, tests_app/test_playbook_routes.py.
