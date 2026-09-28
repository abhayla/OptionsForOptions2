---
work_item: W-001
ac: AC-4
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/engine/test_formulas.py; attack script"
---

AC: AC-4
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/engine/test_formulas.py; attack script
observed: live BUY PE -322.50, SELL PE 1012.50, FUT +/-22500; 0.1->0.2 x3 = Decimal('0.3') exactly
attack: live_pnl on SELL FUT with no LTP raises 'live P&L needs an LTP'; a strategy with one leg missing its LTP raises

Recorded by the orchestrator from the verifier's returned block.
