---
work_item: W-002
ac: AC-2
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/engine/test_inputs.py; dataclasses.fields(LegInput/StrategyInput)"
---

AC: AC-2
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/engine/test_inputs.py; dataclasses.fields(LegInput/StrategyInput)
observed: 23 passed; LegInput and StrategyInput carry every REQ-032 AC-2 input; live P&L 1365.00
attack: bad greeks type refused; float-built premium and ltp refused via the paise guard

Recorded by the orchestrator from the verifier's returned block.
