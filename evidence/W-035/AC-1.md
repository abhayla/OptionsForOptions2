---
work_item: W-035
ac: AC-1
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/admin/test_qualifying_list.py tests/admin/test_qualifying_import.py; python -c (normalise_client_id probes from backend/); python -m pytest -q -p no:cacheprovider"
---

AC: AC-1
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/admin/test_qualifying_list.py tests/admin/test_qualifying_import.py; python -c (normalise_client_id probes from backend/); python -m pytest -q -p no:cacheprovider
observed: 62 passed for the two admin test files; full suite 1283 passed. AB1234, ABC123, ab1234 and ' abc123\t' all return upper-case. AB123, AB12345, A12345, ABCD12, AB12C4, 12AB34, '', 'AB 1234' all raise MalformedClientIdError.
attack: Full-width letters and digits, Arabic-Indic digits, NBSP suffix, NUL, None and bytes are all refused. 'AB1234\n', 'AB1234\r\n' and '\nAB1234' are refused, and ' AB1234 ' is trimmed. The old shapes XYZ123456 and AB1234567 are refused.

Recorded by the orchestrator from the verifier's returned block.
