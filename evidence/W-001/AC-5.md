---
work_item: W-001
ac: AC-5
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/engine/test_formulas.py; attack script"
---

AC: AC-5
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/engine/test_formulas.py; attack script
observed: OTM cells -3300.00 and -3187.50 asserted; grid None? False, all cells type Decimal
attack: grid with levels 0 and 99999 plus a FUT leg: no None cells; a None level and an empty level list both raise ValueError

Recorded by the orchestrator from the verifier's returned block.
