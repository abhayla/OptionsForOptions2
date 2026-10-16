---
work_item: W-087
ac: AC-3
requirement: REQ-001
ac_fp: "376994d0ac6c"
result: pass
verified_by: "verifier (sonnet/high, fresh context, docs/gc-1-closeout b643356)"
builder: "none (verify-only card; code on main)"
date: '2026-10-16'
commands: "python -m pytest -q -p no:cacheprovider tests/instruments/test_broker_identity.py::test_one_broker_code_vocabulary_unknown_codes_refused tests/broker/test_session_lifecycle.py::test_only_zerodha_and_a_user_ref; python tools/ac_fp.py REQ-001 AC-3 --yaml; Grep -i upstox|angel one|dhan|groww|paytm|fyers|5paisa over backend/*.py and frontend/src"
---

AC: AC-3
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/instruments/test_broker_identity.py::test_one_broker_code_vocabulary_unknown_codes_refused tests/broker/test_session_lifecycle.py::test_only_zerodha_and_a_user_ref; python tools/ac_fp.py REQ-001 AC-3 --yaml; Grep -i upstox|angel one|dhan|groww|paytm|fyers|5paisa over backend/*.py and frontend/src
observed: both passed within the 175; test asserts BROKER_CODES == frozenset({'zerodha'}) and that 'upstox','Zerodha','kite','',None raise MissingBrokerRef; start(..., broker='upstox') raises ValueError; backend grep hit only an unrelated '_silent' in kite_ws.py; frontend grep found 0
attack: Searched code for any other broker name or integration (none) and read the test for case variants ('Zerodha' with a capital) and None being refused, not just one bad code.

Recorded by the orchestrator from the verifier's returned block.
