---
work_item: W-021
ac: AC-1
requirement: REQ-060
ac_fp: "15a4b9058e7f"
result: fail
verified_by: "verifier (opus, fresh context, GC-3 P0 item 7, main 85e38e0, 2026-10-17)"
builder: "builders (W-021, W-037, W-085; live path W-095, W-096)"
date: '2026-10-17'
commands: "python -m pytest -q -p no:cacheprovider tests/reconciliation/test_triggers.py tests/reconciliation/test_compare.py tests/reconciliation/test_expiry_settlement.py (102 passed); grep backend/ofo_app for plan_run, Trigger, lifespan, reconnect, periodic, on_order_update"
---

AC: AC-1
result: fail
commands: python -m pytest -q -p no:cacheprovider tests/reconciliation/test_triggers.py tests/reconciliation/test_compare.py tests/reconciliation/test_expiry_settlement.py (102 passed); grep backend/ofo_app for plan_run, Trigger, lifespan, reconnect, periodic, on_order_update
observed: The domain triggers.py maps all 7 Q196 events to a whole-account run (plan_run) and passes its tests, but nothing in backend/ofo_app calls plan_run or Trigger. On the live path reconciliation runs only inside the return route (execution_return.py:165) and Execute (execute.py:470), on the user's click; the kite_ws reconnect starts none; no app-start, resume, periodic or order-event run exists.
attack: searched for any caller on reconnect, start/resume, a periodic tick or an order event: zero call sites. Domain: PERIODIC with nothing active returns None; coverage is every non-exited strategy

GC-3 P0 item 7: re-verification on main of criteria whose evidence predated fingerprints.
Recorded by the orchestrator from the verifier's returned block.
