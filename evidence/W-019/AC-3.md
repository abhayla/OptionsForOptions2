---
work_item: W-019
ac: AC-3
result: pass
verified_by: "verifier (opus, fresh context; round 3 after independent review)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/orders/test_state_not_from_orders.py; attack script; read backend/ofo/orders/model.py"
---

AC: AC-3
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/orders/test_state_not_from_orders.py; attack script; read backend/ofo/orders/model.py
observed: 4 passed; Order stores no filled quantity; filled quantity, state and position computed from FillLedger on every read; derive_strategy_position refuses a non-OrderBook source
attack: no order row can reach Executed without a ledger fill; the property test asserts position == signed ledger sum after every call. Weak test noted: test_executed_order_row_without_a_fill_event_changes_nothing checks an empty book

Recorded by the orchestrator from the verifier's returned block.
