---
work_item: W-211
requirement: REQ-167
ac: AC-2
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "0d76bf1dfa4d"
commands: "read backend/ofo_app/routes/settings.py; read backend/ofo/settings/__init__.py check_value; cd frontend && npx vitest run tests/settings-page.test.js tests/settings-values.test.js"
---
vitest 21/21. GET /api/settings returns group, value in force, default, effective_from, set_by and earlier values (in force / scheduled / earlier); check_value gives the fraction hint for 6.5 on a fraction unit; reset writes a new row at the default with no delete route; back-dated times are refused; Charges comes from its own dated table with source_url. Attack: a JSON number instead of a string is refused (StrictStr).

DB proof owed: tests_app/test_settings_route.py.
