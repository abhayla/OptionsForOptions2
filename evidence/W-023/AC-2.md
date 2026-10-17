---
work_item: W-023
ac: AC-2
requirement: REQ-058
ac_fp: "5610ff177cc9"
result: fail
verified_by: "verifier (opus, fresh context, GC-3 P0 item 7, main 85e38e0, 2026-10-17)"
builder: "builders (W-023, W-028, W-036, W-043)"
date: '2026-10-17'
commands: "python -m pytest -q -p no:cacheprovider tests/execution/test_partial.py; scratch attack.py A1/A6; grep choices in frontend/src; read ReturnCheck.vue, routes/execute.py _executable, ofo/execution/context.py EXECUTABLE_VERSION_STATES"
---

AC: AC-2
result: fail
commands: python -m pytest -q -p no:cacheprovider tests/execution/test_partial.py; scratch attack.py A1/A6; grep choices in frontend/src; read ReturnCheck.vue, routes/execute.py _executable, ofo/execution/context.py EXECUTABLE_VERSION_STATES
observed: Domain CHOICE_ORDER is the four in order, only in PARTIAL_EXCEPTION; the API's er.PARTIAL_CHOICES is in order and _plan_out returns it for a partial plan, but frontend/src has 0 references to 'choices' (ReturnCheck.vue renders only 'Plan N (ENTRY): partial'), and on the basket path Complete/Retry are an ENTRY while held: SUPERSEDED, refused gate_version_not_executable (ADR-105).
attack: after a partial basket the user is never shown the four choices; two of four cannot execute on the basket path; only EXIT (Close) works

GC-3 P0 item 7: re-verification on main of criteria whose evidence predated fingerprints.
Recorded by the orchestrator from the verifier's returned block.
