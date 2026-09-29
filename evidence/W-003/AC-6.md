---
work_item: W-003
ac: AC-6
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/scenario/test_modes.py; attack script"
---

AC: AC-6
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/scenario/test_modes.py; attack script
observed: At Expiry default, exact, equal to an independent §1 recomputation at all 24 columns (Decimal); Estimated Now labelled estimate with model assumptions; missing IV -> unavailable with a reason naming the contract
attack: missing IV gives 'unavailable', never a silent zero; futures-only strategy stays available; a 3-decimal breakeven is estimated at the 0.01-rounded level

Recorded by the orchestrator from the verifier's returned block.
