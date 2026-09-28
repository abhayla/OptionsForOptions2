---
work_item: W-002
ac: AC-1
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/engine/test_single_engine.py; grep for BUY/SELL sign formulas in backend/ofo; estimate_now attack script"
---

AC: AC-1
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/engine/test_single_engine.py; grep for BUY/SELL sign formulas in backend/ofo; estimate_now attack script
observed: 5 passed; only sign formula legs.py:110 position_pnl; metrics._upper_tail_slope via legs.position_pnl; flipping the convention changes grid, live, estimate together and swaps condor max profit/loss 6825/8175 -> 8175/6825; estimate leg P&Ls at 23200 = golden §6 live values
attack: SELL vs BUY sign in the estimate per leg; breakeven with 3+ dp into estimate_now refused, metrics breakevens are 2 dp and accepted (W-003 must use metrics output)

Recorded by the orchestrator from the verifier's returned block.
