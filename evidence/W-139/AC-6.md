---
work_item: W-139
ac: AC-6
requirement: REQ-114
ac_fp: "d27cd83604e0"
result: pass
verified_by: "independent verifiers (Opus, fresh context; round 1 on b04d47f0, round 2 on 0e574b58)"
builder: "builders (Sonnet/Opus, builder sequence row 11: build, fix 1)"
date: '2026-10-23'
commands: "round 2 on 0e574b58: pytest -c pytest-app.ini tests_app/test_kite_ws.py tests_app/test_broker_status_route.py -k 'token or closed or market' (7 passed)"
---

AC: AC-6
result: pass
commands: round 2 on 0e574b58: pytest -c pytest-app.ini tests_app/test_kite_ws.py tests_app/test_broker_status_route.py -k 'token or closed or market' (7 passed)
observed: kite_ws.py:84 allow-list TokenException|access_token inside an error frame only; 'Invalid instrument token 123', 'Too many requests', empty, non-JSON keep the session (test_kite_ws.py:269-285)
attack: instrument-token and unknown error texts sent through the real socket; session lives

Recorded by the orchestrator from the verifier's returned block.
