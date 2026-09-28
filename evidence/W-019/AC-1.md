---
work_item: W-019
ac: AC-1
result: pass
verified_by: "verifier (opus, fresh context; round 3 after independent review)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/orders/test_lifecycle.py; attack script against ofo.orders (16b571b)"
---

AC: AC-1
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/orders/test_lifecycle.py; attack script against ofo.orders (16b571b)
observed: 15 passed; exactly 7 states; Executed->Cancelled refused; transition() to Executed/Partially Executed refused; no filled_delta argument (TypeError); add() of a Submitted order refused; Partially Executed -> Cancelled allowed, a later fill refused, identical replay a no-op
attack: cancel a fully filled order; reach Executed via transition() or add(): refused. Residual (deferred issue): ALLOWED_TRANSITIONS is a mutable exported dict

Recorded by the orchestrator from the verifier's returned block.
