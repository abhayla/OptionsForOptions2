---
work_item: W-143
ac: AC-2
requirement: REQ-028
ac_fp: "783bc84b622b"
result: fail
verified_by: "independent verifiers (Opus, fresh context, start check on 0e574b58; Sonnet, fresh context, AC-2 on 025a22cf)"
builder: "builders (earlier work items; builder sequence row 15 start check, no new code)"
date: '2026-10-23'
commands: "AC-2 check (Sonnet, fresh) on 025a22cf: pytest tests/strategy tests/execution tests/adjustment (1289 passed); grep backend/ofo_app for each type; scratch attack.py"
---

AC: AC-2
result: fail
commands: AC-2 check (Sonnet, fresh) on 025a22cf: pytest tests/strategy tests/execution tests/adjustment (1289 passed); grep backend/ofo_app for each type; scratch attack.py
observed: execution plan represented and used (execution/planned.py:39, execute_plan.py:173); modification reaches the app only as a pending Version (LegChange/propose_modification, modification.py:79,:232, never called); exit domain type mark_exited (versions.py:673) has no app caller, the app exits through ep.exit_legs (execute_plan.py:230); adjustment proposal (rules/actions.py:29) has no app path, respond() raises for ADJUSTMENT (:67). Issue #528
attack: invalid modifications and an empty plan refused; Proposal('', 'r', ()) and ProposedOrder(qty=-3, strike=-5) accepted (no validation)

Recorded by the orchestrator from the verifier's returned block.
