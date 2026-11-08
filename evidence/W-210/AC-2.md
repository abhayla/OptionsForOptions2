---
work_item: W-210
requirement: REQ-163
ac: AC-2
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "a6824e0c5674"
commands: "python -m pytest -q -p no:cacheprovider tests/engine/test_adjust_history.py tests/test_history_not_shown.py; read backend/ofo/engine/adjust_history.py _totals"
---
pytest 100 passed. _totals computes every figure from the rows and asserts each against the engine book; open P&L, P&L and premium left are None with a named reason when prices are missing, never 0; an unequal total raises HistoryMismatch; money is Decimal with float refused (ADR-008); the route does no arithmetic. Attack: pending rows and missing prices give None, not a default.

DB proof owed: tests_app/test_adjustment_history.py::test_adj13_history_rows_and_totals_equal_the_domain_and_the_generator.

Recorded by the orchestrator from the verifier's returned block.
