---
work_item: W-019
ac: AC-2
requirement: REQ-057
ac_fp: "7f475588405f"
result: pass
verified_by: "verifier (opus, fresh context, GC-3 P0 item 7, main 85e38e0, 2026-10-17)"
builder: "builder (W-019)"
date: '2026-10-17'
commands: "python -m pytest -q -p no:cacheprovider tests/orders/test_no_state_before_fill.py; scratch attack script; python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_execution_return.py -k \"not app_engine and not core_real_order_return and not recorded_once and not core_another_strategys_open_plan and not plan_from_yesterday\" (31 passed, 4 DB tests deselected - run in CI)"
---

AC: AC-2
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/orders/test_no_state_before_fill.py; scratch attack script; python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_execution_return.py -k "not app_engine and not core_real_order_return and not recorded_once and not core_another_strategys_open_plan and not plan_from_yesterday" (31 passed, 4 DB tests deselected - run in CI)
observed: Submitted/Pending leave position 0, no fills; a broker EXECUTED/PARTIALLY_EXECUTED status without a fill leaves Submitted and position {}. Live return path on the real replies orders-122104 + trades-122104: COMPLETE order with its trade -> filled {'OFS1V1L0': 65}; OPEN 30 of 65 -> waiting {} (nothing stored); unknown status 'TRIGGER PENDING' -> waiting {}; REJECTED 0 filled -> nothing_placed {0}.
attack: partial then CANCELLED with a 30-unit trade -> partial {30}; CANCELLED showing 30 filled with no trade row -> reconciliation_required {}; REJECTED 0 filled with a 65-unit trade row -> reconciliation_required {}; fill with an unknown broker order id -> ValueError, fill count unchanged

GC-3 P0 item 7: re-verification on main of criteria whose evidence predated fingerprints.
Recorded by the orchestrator from the verifier's returned block.
