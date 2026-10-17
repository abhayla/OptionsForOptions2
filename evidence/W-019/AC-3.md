---
work_item: W-019
ac: AC-3
requirement: REQ-057
ac_fp: "57e4290872d2"
result: pass
verified_by: "verifier (opus, fresh context, GC-3 P0 item 7, main 85e38e0, 2026-10-17)"
builder: "builder (W-019)"
date: '2026-10-17'
commands: "python -m pytest -q -p no:cacheprovider tests/orders/test_state_not_from_orders.py; scratch attack script"
---

AC: AC-3
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/orders/test_state_not_from_orders.py; scratch attack script
observed: Position computed only from FillLedger + adopted holdings (model.py:687-696); derive_strategy_position refuses anything not an OrderBook; refuse_position_from_orders always raises. Live path: execution_return._agrees (:94-97) accepts an order row's filled_quantity only when it equals the de-duplicated trades for that order id; strategy state = stored plan fills (held_units) checked against Zerodha positions (reconcile).
attack: a real COMPLETE 65/65 order row with an EMPTY trades list -> reconciliation_required {}, never filled; a forged Executed Order via object.__setattr__ into OrderBook.add refused (existing test passes). Residual (deferred issue): an order that appears between the orders read and the trades read has its trade dropped (execution_return.py:164)

GC-3 P0 item 7: re-verification on main of criteria whose evidence predated fingerprints.
Recorded by the orchestrator from the verifier's returned block.
