---
work_item: W-116
ac: AC-1
requirement: REQ-029
ac_fp: "b0abe057d492"
result: fail
verified_by: "verifier (opus, fresh context, Tier A; round 1 ff7cf11 FAIL, round 2 6562054, 2026-10-19)"
builder: "builder (W-116, opus, 2 rounds)"
date: '2026-10-19'
commands: "python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_chain_live.py tests_app/test_response_door.py tests_app/test_openapi_drift.py; scratch b1.py (w116-attack2)"
---

AC: AC-1
result: fail
commands: python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_chain_live.py tests_app/test_response_door.py tests_app/test_openapi_drift.py; scratch b1.py (w116-attack2)
observed: 261 passed; rows ascending by strike with a ce and pe cell each for the requested underlying and expiry; recentre rows 25300..25400. BACKEND PART PROVEN: the row data and its order. NOT MET AS WRITTEN: no screen in W-116 (layout is item 4b, W-118).
attack: Round 1 (ff7cf11) FAILED with a MAJOR error storm (30 errors in 30 loops); round 2 (6562054): re-centre, expiry change and an unknown contract kept the Calls | Strike | Puts shape; 30 s mixed load never sent 2 messages within 1 s.

Recorded by the orchestrator from the verifier's returned block.
