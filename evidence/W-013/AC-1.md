---
work_item: W-013
ac: AC-1
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/rules tests/engine/test_net_premium.py; python -m pytest -q -p no:cacheprovider"
---

AC: AC-1
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/rules tests/engine/test_net_premium.py; python -m pytest -q -p no:cacheprovider
observed: 51 passed; 109 passed; one Rule type for ENTRY/ADJUSTMENT/EXIT evaluated by evaluate()
attack: exit rule with Always() and a rule with no action both raise; int threshold refused

Recorded by the orchestrator from the verifier's returned block.
