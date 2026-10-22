---
work_item: W-128
ac: AC-7
requirement: REQ-082
ac_fp: "6a490df9c349"
result: pass
verified_by: "independent Tier A verifier (Opus, fresh context)"
builder: "builder (Sonnet, lane B cluster B4)"
date: '2026-10-22'
commands: "db_run pytest tests_app/test_production_config_switches.py; verified sha 0f1704039dbe4f6e471c64e20776ef96e85f8404"
---

AC: AC-7
result: pass
commands: db_run pytest tests_app/test_production_config_switches.py; verified sha 0f1704039dbe4f6e471c64e20776ef96e85f8404
observed: example configuration as production -> features_on() == (); the probability switch needs a reference
attack: ignore-reference mutation turned the production tests red

Recorded by the orchestrator from the verifier's returned block.
