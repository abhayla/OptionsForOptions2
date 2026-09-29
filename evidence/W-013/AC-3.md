---
work_item: W-013
ac: AC-3
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "pytest tests/rules/test_exit.py; stdin boundary script"
---

AC: AC-3
result: pass
commands: pytest tests/rules/test_exit.py; stdin boundary script
observed: max loss -5000 TRIGGERED, -4999.99 NOT, -5000.01 TRIGGERED; profit 3000 TRIGGERED, 2999.99 NOT
attack: missing action -> TypeError; alert+prepare builds a Proposal needing user confirmation; no order placement in rules/

Recorded by the orchestrator from the verifier's returned block.
