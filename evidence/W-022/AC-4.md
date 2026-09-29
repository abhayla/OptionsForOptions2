---
work_item: W-022
ac: AC-4
result: pass
verified_by: "verifier (opus, fresh context; second check W-022b)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/execution/test_plan_failures.py; simulate() over every golden condor failure subset"
---

AC: AC-4
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/execution/test_plan_failures.py; simulate() over every golden condor failure subset
observed: 22,800 PE failure withholds only the 23,000 PE sale; both wings failing -> no sale sent; a failing future withholds its covered call/put; transitive withholding works
attack: direct-only withholding and >= naked threshold mutants killed. Note: failure is tracked per leg; a failed protective slice must map to a failed leg once an executor exists

Recorded by the orchestrator from the verifier's returned block.
