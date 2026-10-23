---
work_item: W-144
ac: AC-5
requirement: REQ-038
ac_fp: "9b49fc3acd93"
result: pass
verified_by: "independent verifiers (Opus, fresh context; round 1 on d99b2097, round 2 on 735ba1a6; DB part CI #525 on f5a1059c)"
builder: "builders (Opus, builder sequence row 16: build, fix 1)"
date: '2026-10-23'
commands: "start check on 0e574b58 (dumps/loads exact, M5 killed); round 2: pytest -c pytest-app.ini tests_app/test_response_door.py tests_app/test_openapi_drift.py (213 passed); DB part CI #525"
---

AC: AC-5
result: pass
commands: start check on 0e574b58 (dumps/loads exact, M5 killed); round 2: pytest -c pytest-app.ini tests_app/test_response_door.py tests_app/test_openapi_drift.py (213 passed); DB part CI #525
observed: before execution load is unchanged; after execution GET/PUT answer the active definition plus every version with its own definition, so a proposal reads back (routes/strategies.py:149-150, :269-277); old versions read with require_live=False (stored_form.py:461)
attack: saved quantity 130 after a fill reads back in the proposed version while the active stays 65

Recorded by the orchestrator from the verifier's returned block.
