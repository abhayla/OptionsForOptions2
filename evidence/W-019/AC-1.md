---
work_item: W-019
ac: AC-1
requirement: REQ-057
ac_fp: "ecad682a8459"
result: pass
verified_by: "verifier (opus, fresh context, GC-3 P0 item 7, main 85e38e0, 2026-10-17)"
builder: "builder (W-019)"
date: '2026-10-17'
commands: "python -m pytest -q -p no:cacheprovider tests/orders (76 passed); python -m pytest -q -p no:cacheprovider tests/orders/test_lifecycle.py tests/orders/test_no_state_before_fill.py tests/orders/test_state_not_from_orders.py (42 passed); scratch attack script (verify-req057/attack.py)"
---

AC: AC-1
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/orders (76 passed); python -m pytest -q -p no:cacheprovider tests/orders/test_lifecycle.py tests/orders/test_no_state_before_fill.py tests/orders/test_state_not_from_orders.py (42 passed); scratch attack script (verify-req057/attack.py)
observed: OrderState has exactly the 7 states (backend/ofo/orders/model.py:50-57); ALLOWED_TRANSITIONS (:71-94) read-only with a row per state; Executed, Rejected, Cancelled have no exits; Partially Executed / Executed reachable only through a ledger fill (transition() refuses at :235, :571). Partial 30 of 65 -> Partially Executed filled 30; cancel after partial -> Cancelled, position kept 30; fill after cancel refused; Prepared->Pending refused; Rejected->Submitted refused. Note: the live Execute/return routes do not use OrderState/OrderBook; they guard with Kite's terminal status allow-list plus order-row-vs-trades agreement.
attack: broker REJECTED after a partial fill -> refused 'Partially Executed -> Rejected is not an allowed order transition', position stays 30; fill on a never-submitted Prepared order refused, 0 fills; fill on Rejected refused

GC-3 P0 item 7: re-verification on main of criteria whose evidence predated fingerprints.
Recorded by the orchestrator from the verifier's returned block.
