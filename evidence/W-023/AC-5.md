---
work_item: W-023
ac: AC-5
result: pass
verified_by: "verifier (opus, fresh context, rounds 3-4) and verifier (sonnet, mutation checks W-023e/W-023f)"
builder: "builder (opus); rounds 4-6 tests by builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/execution/test_complete.py"
---

AC: AC-5
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/execution/test_complete.py
observed: all orders submitted -> not complete; broker EXECUTED without a ledger fill -> RECONCILIATION_REQUIRED; COMPLETE only when positions equal the plan
attack: timeout then broker EXECUTED without a fill -> mismatch, zero orders prepared, one send

Recorded by the orchestrator from the verifier's returned block.
