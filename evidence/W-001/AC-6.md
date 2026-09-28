---
work_item: W-001
ac: AC-6
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/engine/test_metrics.py; attack script"
---

AC: AC-6
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/engine/test_metrics.py; attack script
observed: 10 passed; ratio BUY 1x23000CE@100 / SELL 2x23200CE@40 qty 75 -> BE (23020, 23380), max_profit 13500, max_loss UNLIMITED, payoff at both BEs = 0; short call max_loss UNLIMITED; short put max_loss 1719000 (finite, from Market 0)
attack: breakeven exactly at a strike (bear put 23100/23000, debit 100) -> (23000,), level 0 excluded; 3x/7x ratio gives 23076.67 (rounded) and 23292.5 (exact), both match hand values; multi-expiry raises MultiExpiryError; Leg has no breakeven or max fields

Recorded by the orchestrator from the verifier's returned block.
