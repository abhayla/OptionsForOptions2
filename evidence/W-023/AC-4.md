---
work_item: W-023
ac: AC-4
requirement: REQ-058
ac_fp: "0e0ca808e7e5"
result: fail
verified_by: "verifier (opus, fresh context, GC-3 P0 item 7, main 85e38e0, 2026-10-17)"
builder: "builders (W-023, W-028, W-036, W-043)"
date: '2026-10-17'
commands: "python -m pytest -q -p no:cacheprovider tests/execution/test_complete.py tests/execution/test_in_flight.py tests/execution/test_order_sync.py tests/execution/test_complete_slices.py tests/execution/test_close_refusals.py tests/execution/test_complete_refusals.py tests/execution/test_no_retry.py tests/execution/test_duplicate_order_guards.py (115 passed); scratch verify-req058b/attack.py; grep complete_strategy, retry_failed_leg, close_partial_strategy in backend/ofo_app and frontend/src"
---

AC: AC-4
result: fail
commands: python -m pytest -q -p no:cacheprovider tests/execution/test_complete.py tests/execution/test_in_flight.py tests/execution/test_order_sync.py tests/execution/test_complete_slices.py tests/execution/test_close_refusals.py tests/execution/test_complete_refusals.py tests/execution/test_no_retry.py tests/execution/test_duplicate_order_guards.py (115 passed); scratch verify-req058b/attack.py; grep complete_strategy, retry_failed_leg, close_partial_strategy in backend/ofo_app and frontend/src
observed: The domain complete_strategy (backend/ofo/execution/partial.py:720) re-reads positions, order statuses, available margin and Zerodha's required margin and prepares only the missing leg. Nothing in backend/ofo_app or frontend/src calls complete_strategy, retry_failed_leg or close_partial_strategy; the only app mention is the identifier list PARTIAL_CHOICES (ofo_app/execution_return.py:49). The only order route refuses an ENTRY while held (version_state SUPERSEDED), so after a partial ENTRY no route builds a basket for the missing legs.
attack: domain: a 61 s old status read prepares nothing; a float margin fails closed; an unknown open order on the missing contract gives waiting for reconciliation; the missing leg held on the wrong side prepares nothing. Platform: Complete Strategy is not wired into any route, so 'submits only the required order(s)' cannot happen on main

GC-3 P0 item 7: re-verification on main of criteria whose evidence predated fingerprints.
Recorded by the orchestrator from the verifier's returned block.
