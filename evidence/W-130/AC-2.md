---
work_item: W-130
ac: AC-2
requirement: REQ-015
ac_fp: "0d24350fa7a3"
result: pass
verified_by: "independent verifier (Opus, fresh context, round 2 on 8a23776f)"
builder: "builder (Sonnet, builder sequence row 2)"
date: '2026-10-22'
commands: "round 2: pytest tests_app/test_connect_gate_routes.py tests/errors/test_connect_prompt.py; orchestrator db_run pytest test_connect_gate_routes.py (49 passed with 3 more row-2 files)"
---

AC: AC-2
result: pass
commands: round 2: pytest tests_app/test_connect_gate_routes.py tests/errors/test_connect_prompt.py; orchestrator db_run pytest test_connect_gate_routes.py (49 passed with 3 more row-2 files)
observed: the exact AC sentence is gate_broker_not_connected (templates.py:327), answered with no stored session by execute (execute.py:298), execution return (execution_return.py:140) and positions (positions.py:169); an unreadable stored session answers gate_broker_unconfirmed from get_kite_session
attack: round 1 found execute/return answering 'unconfirmed' with no session (fixed 8a23776f); order: an unreadable session now refuses before the strategy 404 (accepted: one owner, fails closed)

Recorded by the orchestrator from the verifier's returned block.
