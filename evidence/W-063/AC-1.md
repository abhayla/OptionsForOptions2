---
work_item: W-063
ac: AC-1
requirement: REQ-034
ac_fp: "4313460d7e3c"
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (opus)"
date: '2026-10-08'
commands: "python -m pytest -c pytest-app.ini -q -p no:cacheprovider tests_app/test_outcome_route.py; python -m pytest -q -p no:cacheprovider (full); ad-hoc python script replaying the frames and POSTing the condor via ASGI, comparing to an independent REQ-033 AC-1 Decimal formula"
---

AC: AC-1
result: pass
commands: python -m pytest -c pytest-app.ini -q -p no:cacheprovider tests_app/test_outcome_route.py; python -m pytest -q -p no:cacheprovider (full); ad-hoc python script replaying the frames and POSTing the condor via ASGI, comparing to an independent REQ-033 AC-1 Decimal formula
observed: 5 passed (pytest-app.ini); full suite 1799 passed; HTTP 200, max_profit 4754.75, max_loss 8245.25, breakevens 22326.85/22873.15, payoff at 22300 = -1745.25 (equals the formula); margin NOT_AVAILABLE_YET; no JSON float (parse_float hook never fired); OpenAPI has no float/number types
attack: Called with no provider: state NOT_CONNECTED, label 'Draft - Live data not connected', HTTP 200, not an error. Float planned_entry returns 422. A stale leg is labelled 'stale since HH:MM IST'. OutcomeLeg reaches no order/broker path (used only in serialize.py). Under the root pytest.ini the route tests fail for lack of an asyncio mode; the same happens to test_health.py, and CI's pytest-app.ini passes them.

Recorded by the orchestrator from the verifier's returned block.
