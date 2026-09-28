---
work_item: W-001
ac: AC-2
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/engine/test_formulas.py"
---

AC: AC-2
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/engine/test_formulas.py
observed: test_strategy_pnl_is_sum_of_legs passes incl. hand value 3275.00 at 23150.5 (37.5+4500-1262.5)
attack: grid totals with CE+PE+FUT legs at levels 0/22000/23000.5/99999: totals Decimal (-2224925, -24925, 125.0, 7699975), equal to the leg sums

Recorded by the orchestrator from the verifier's returned block.
