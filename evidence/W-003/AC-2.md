---
work_item: W-003
ac: AC-2
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/scenario/; attack script"
---

AC: AC-2
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/scenario/; attack script
observed: 21 passed; spot on a breakeven -> one column flagged current+zero_pnl; spot on a grid level -> one column; spot 20000.55 -> range 19000..23800 with CURRENT; override 24000..25000 keeps CURRENT at its price position
attack: spot exactly on a breakeven, on a grid level with a different Decimal exponent, outside a user range: CURRENT always present, never duplicated

Recorded by the orchestrator from the verifier's returned block.
