---
work_item: W-211
requirement: REQ-167
ac: AC-3
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "b0a6f214ac57"
commands: "read backend/ofo_app/routes/settings.py require_admin and write routes; read settings_store.add_setting; grep -rn app_settings backend --include=*.py"
---
All three write routes take Depends(require_admin) (single owner until sign-in, as the AC allows); add_setting inserts the row and an ADMIN_CHANGE_RECORDED audit event in one savepoint; the charges route also audits; no other module writes app_settings. Attack: a duplicate-time insert or an audit failure rolls back both.

DB proof owed: tests_app/test_settings_route.py (ac3 tests).
