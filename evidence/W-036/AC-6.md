---
work_item: W-036
ac: AC-6
requirement: REQ-058
ac_fp: "9e4db8068e48"
result: fail
verified_by: "verifier (opus, fresh context, GC-3 P0 item 7, main 85e38e0, 2026-10-17)"
builder: "builders (W-023, W-028, W-036, W-043)"
date: '2026-10-17'
commands: "python -m pytest -q -p no:cacheprovider tests/execution/test_close_refusals.py tests/execution/test_complete_refusals.py tests/execution/test_no_retry.py; scratch app_attack.py; grep status_message in backend/ofo_app and status_message, rejection, nothing_placed, choices in frontend/src; read routes/execution_return.py ReturnPlanOut and _plan_out"
---

AC: AC-6
result: fail
commands: python -m pytest -q -p no:cacheprovider tests/execution/test_close_refusals.py tests/execution/test_complete_refusals.py tests/execution/test_no_retry.py; scratch app_attack.py; grep status_message in backend/ofo_app and status_message, rejection, nothing_placed, choices in frontend/src; read routes/execution_return.py ReturnPlanOut and _plan_out
observed: Domain passes: a transport timeout gives exactly 1 send with failed 'outcome unknown: read timed out'; a second submit of the same preparation raises; assess() shows the RMS text with the four choices. Live path: a Kite row REJECTED with status_message 'RMS:Margin Exceeds...' is classified nothing_placed with reason None, the same as a basket the user closed; ReturnPlanOut's reason may only be 'plan_from_earlier_session'; audit_allowlist.py:39-40 drops status_message; frontend/src has no hit for status_message. The no-resubmission half holds (the platform sends no order, ADR-054).
attack: fed a REJECTED-with-reason row through the live classify(): the user gets nothing_placed and no reason and cannot tell a margin rejection from an abandoned basket; resend attacks (unknown outcome, double submit) held

GC-3 P0 item 7: re-verification on main of criteria whose evidence predated fingerprints.
Recorded by the orchestrator from the verifier's returned block.
