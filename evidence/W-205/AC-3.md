---
work_item: W-205
requirement: REQ-158
ac: AC-3
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "21a5018bd134"
commands: "grep -n playbook_name_taken backend; read playbook_store.py:185-200,430-455; read templates.py:1275"
---
Not verified in budget. Seen: _NAME_USED compares lower(name) per user and type (playbook_store.py:191); create and rename (_write_named) raise playbook_name_taken (437-450); the text 'A playbook named {name} already exists for {type}.' (templates.py:1275) matches the AC. Not read: whether duplicate reuses _write_named, and the delete path.

DB proof owed: tests_app/test_playbook_store.py, tests_app/test_playbook_routes.py (name clash, duplicate, delete).

Recorded by the orchestrator from the verifier's returned block.
