---
work_item: W-003
ac: AC-5
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/scenario/test_levels.py; attack script"
---

AC: AC-5
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/scenario/test_levels.py; attack script
observed: golden inserted columns 22909 zero_pnl, 23047 current, 23491 zero_pnl; SENSEX step 300 on real fixture strikes 74700..76500, BEs 75065/76135; 3-BE ratio all inserted; single-BE Lower/Upper labelling correct
attack: breakeven on a grid level gets a flag, not a second column; 3 breakevens; no-BE case; levels are Decimal points, no rupee formatting

Recorded by the orchestrator from the verifier's returned block.
