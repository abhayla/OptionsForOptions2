---
work_item: W-129
ac: AC-1
requirement: REQ-001
ac_fp: "e444ac3f8bad"
result: pass
verified_by: "independent verifier (Sonnet, fresh context, round 2 on 3162e50f)"
builder: "builder (Sonnet, builder sequence row 1)"
date: '2026-10-22'
commands: "verifier round 2 on 3162e50f: attack.py (ASGI, 5 values x 8 routes); pytest tests_app/test_underlying_refusal.py test_strategy_live_push.py test_chain_live.py test_response_door.py test_catalogue_picker_api.py (5 failures = #497 non-empty shared catalogue, count==0 asserts)"
---

AC: AC-1
result: pass
commands: verifier round 2 on 3162e50f: attack.py (ASGI, 5 values x 8 routes); pytest tests_app/test_underlying_refusal.py test_strategy_live_push.py test_chain_live.py test_response_door.py test_catalogue_picker_api.py (5 failures = #497 non-empty shared catalogue, count==0 asserts)
observed: NIFTY/SENSEX part only (the BANKNIFTY/FINNIFTY part is deferred to row 46, REQ-090, which re-verifies AC-1): BANKNIFTY, nifty, N1FTY -> 422 USER_INPUT_101 'X is not supported. Supported underlyings: NIFTY, SENSEX.' echoed as typed on outcome, save, planned-entry, chain and both catalogue routes; 'NIFTY ' and '' -> fixed USER_INPUT_002, never echoed; held routes answer 409 before the body, their body models give 101; no stock option, screener or heatmap
attack: outside values on every route and socket; round 1 found a stale picker test (fixed in 3162e50f)

Recorded by the orchestrator from the verifier's returned block.
