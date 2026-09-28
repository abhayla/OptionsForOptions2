---
work_item: W-001
ac: AC-7
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/engine/test_golden_iron_condor.py"
---

AC: AC-7
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/engine/test_golden_iron_condor.py
observed: 3 passed; asserts live -322.50/1012.50/1012.50/-337.50, total 1365.00, max profit 6825, max loss 8175, BEs 22909/23491, 21 levels, 4 per-leg samples
attack: hand-recomputed every section 6 number (net credit 91, (200-91)x75=8175, 22900 = -9x75 = -675, leg2 at 22000 = (86-1000)x75 = -68550, leg4 at 24000 = 356x75 = 26700): all match

Recorded by the orchestrator from the verifier's returned block.
