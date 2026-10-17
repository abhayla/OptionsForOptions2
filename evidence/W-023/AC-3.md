---
work_item: W-023
ac: AC-3
requirement: REQ-058
ac_fp: "59143b62b1f1"
result: pass
verified_by: "verifier (opus, fresh context, GC-3 P0 item 7, main 85e38e0, 2026-10-17)"
builder: "builders (W-023, W-028, W-036, W-043)"
date: '2026-10-17'
commands: "python -m pytest -q -p no:cacheprovider tests/execution/test_partial.py; grep place_order, orders/regular, cancel_order, modify_order in backend/ofo_app (0 hits); scratch attack.py A1-A7; read routes/execution_return.py, execute_plan.exit_legs and held_units"
---

AC: AC-3
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/execution/test_partial.py; grep place_order, orders/regular, cancel_order, modify_order in backend/ofo_app (0 hits); scratch attack.py A1-A7; read routes/execution_return.py, execute_plan.exit_legs and held_units
observed: test_ac3_filled_legs_never_unwound_automatically passes; ofo_app has no order-placing, cancel or modify call; the return route only reads Zerodha and closes the plan record (waiting/reconcile leave it open); exit = net over all plans: held +65 gives SELL 65; CANCELLED 30/65 gives partial filled 30; a partly filled exit 30/65 leaves held 35; after a full exit a second EXIT is refused; filled_quantity 30 with no trades gives reconciliation_required; OPEN gives waiting; next day gives reconciliation_required.
attack: a return inside the 15-min window, a cancel after a partial fill, filled_quantity not matching trades, a stale plan, a double exit: every path leaves filled legs untouched until the user presses Execute EXIT, and that exit is exactly the net held

GC-3 P0 item 7: re-verification on main of criteria whose evidence predated fingerprints.
Recorded by the orchestrator from the verifier's returned block.
