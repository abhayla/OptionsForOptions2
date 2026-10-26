---
work_item: W-154
requirement: REQ-081
ac: AC-7
result: pass
verified_by: "independent verifier (Sonnet row 26f check, round 1 at 61fe1325 and round 2 at 77fa79cb, PR #577)"
builder: "builders (Sonnet row 26f 6fe5ad7f, follow-up 77fa79cb)"
date: 2026-10-26
ac_fp: "963ef5cbfe48"
commands: "db_run.py ... pytest tests_app/test_response_door.py; npx vitest run (5 files, 67 passed)"
---
every money key is a string in the reply; the browser parses and compares no money (diff grep 0 hits; '0.1+0.2' and 'NaN' print verbatim)
