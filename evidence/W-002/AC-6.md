---
work_item: W-002
ac: AC-6
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/engine/test_interfaces.py; margin/charges attack"
---

AC: AC-6
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/engine/test_interfaces.py; margin/charges attack
observed: 3 passed; plan_margin returns MarginRequirement; pnl_after_charges exact; stdlib + ofo.engine only
attack: float margin, float-built charge and missing margin source all refused

Recorded by the orchestrator from the verifier's returned block.
