---
work_item: W-003
ac: AC-8
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/scenario/test_single_source.py; attack script"
---

AC: AC-8
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/scenario/test_single_source.py; attack script
observed: spy counts: build_level_set and scenario_values called by both table and graph; graph points == table; 61-column Estimated Now x10 in 0.149 s
attack: both views and the unavailable path share one source; performance well under a second

Recorded by the orchestrator from the verifier's returned block.
