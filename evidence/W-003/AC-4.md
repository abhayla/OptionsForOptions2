---
work_item: W-003
ac: AC-4
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/scenario/test_config.py; attack script"
---

AC: AC-4
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/scenario/test_config.py; attack script
observed: defaults NIFTY 100 / SENSEX 300 as ScenarioConfig; Admin step 200 changes the grid; step 75/150/250 refused by check_against_catalogue against the real fixture; overrides inside bounds accepted, 22000..42000 refused (201 > 200 columns), off-anchor refused, int input refused
attack: Gap (deferred): build_level_set does not call the catalogue check, so a ScenarioConfig with step 75 is accepted directly (no Admin save path exists yet)

Recorded by the orchestrator from the verifier's returned block.
