---
work_item: W-001
ac: AC-3
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/engine/test_formulas.py; attack script"
---

AC: AC-3
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/engine/test_formulas.py; attack script
observed: expiry_pnl at 22000 = 56812.50 for LTP 38.20, 500.00 and none
attack: LTP 0 / 1 / 99999.99 on BUY 23000 CE at 23300: result set {15000}, LTP has no effect

Recorded by the orchestrator from the verifier's returned block.
