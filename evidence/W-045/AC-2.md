---
work_item: W-045
ac: AC-2
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "register_calculator for ids 4,26,28 and for 12,13,19-25,30; get(True/False/1.0/'4')"
---

AC: AC-2
result: pass
commands: register_calculator for ids 4,26,28 and for 12,13,19-25,30; get(True/False/1.0/'4')
observed: 4, 26, 28 accepted; all 10 non-pass ids raised FeasibilityError; bool/float/str ids raised RegistryError
attack: Every non-pass and out-of-V1 row (24, 25) plus a bool id: all refused

Recorded by the orchestrator from the verifier's returned block.
