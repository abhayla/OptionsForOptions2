---
work_item: W-003
ac: AC-3
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/scenario/test_levels.py; attack script"
---

AC: AC-3
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/scenario/test_levels.py; attack script
observed: golden grid 22,000..24,000 step 100 (21 grid + 3 inserted = 24 columns); IV 20%/30d widens to 21,500..24,600; short straddle (UNLIMITED upside) range 22000..24000
attack: unlimited upside: range stays finite and covers both breakevens 22710/23290. Limitation: a default range needing more than 200 columns (strikes 23,000 to 43,000) is refused with an error instead of cut down

Recorded by the orchestrator from the verifier's returned block.
