---
work_item: W-070
ac: AC-2
requirement: REQ-065
ac_fp: "d1023ce348f1"
result: fail
verified_by: "verifier (Opus, independent, Tier A, 2026-10-15)"
builder: "builder (Opus, #200 bounded round, 2026-10-15)"
date: '2026-10-15'
commands: "python -m pytest -q -p no:cacheprovider tests/test_door_names_private.py tests/test_door_rebinding_and_asgi_scan.py; db_run.py . python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_response_door.py tests_app/test_strategy_live_push.py tests_app/test_api_models.py tests_app/test_error_boundary.py tests_app/test_kite_login.py; per-file scanner run over 20 planted routes/pl_*.py; runtime _through_boundary probes; python tools/trace_check.py ."
---

AC: AC-2
result: fail
commands: python -m pytest -q -p no:cacheprovider tests/test_door_names_private.py tests/test_door_rebinding_and_asgi_scan.py; db_run.py . python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_response_door.py tests_app/test_strategy_live_push.py tests_app/test_api_models.py tests_app/test_error_boundary.py tests_app/test_kite_login.py; per-file scanner run over 20 planted routes/pl_*.py; runtime _through_boundary probes; python tools/trace_check.py .
observed: 287 passed; 378 passed; verbatim N1/N2/N3/N5 flagged; variants (e,)=(errors,), def f(m=errors), [errors][0], respond-as-mk, s=r copy: 0 hits; seal-editing wrapper and nowhere-then-reuse: wire got 200 + x-evil: unminted + body 'You should buy NIFTY'; issue N5 raw write -> 500 only; killing tests named
attack: #200 one bounded round (ADR-074, 2026-10-15): covers the class N1-N3: no (three import aliases unflagged); covers the class N5: no (aliased or copied response call unflagged; seal fields writable so a send wrapper edits start/body and seal together and passes). The round is strictly stronger than main (verbatim shapes flagged; raw-write N5 now 500) and is merged PARTIAL; #200 stays parked; REQ-065 is the named open exception at the core gate (ADR-074), Verified before Stage 5.

Recorded by the orchestrator from the verifier's returned block.
