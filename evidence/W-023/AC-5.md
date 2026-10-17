---
work_item: W-023
ac: AC-5
requirement: REQ-058
ac_fp: "81fc90af46b6"
result: pass
verified_by: "verifier (opus, fresh context, GC-3 P0 item 7, main 85e38e0, 2026-10-17)"
builder: "builders (W-023, W-028, W-036, W-043)"
date: '2026-10-17'
commands: "python -m pytest -q -p no:cacheprovider tests/execution/test_complete.py (test_ac5_* x3, in the 115-passed run); scratch verify-req058b/attack.py, app_attack.py"
---

AC: AC-5
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/execution/test_complete.py (test_ac5_* x3, in the 115-passed run); scratch verify-req058b/attack.py, app_attack.py
observed: Domain: assess() sets COMPLETE only when no leg remains missing in the broker positions AND there are no mismatches (partial.py:389-392); SubmissionResult has no completeness field. Live classify() on a 1-leg plan BUY 65 NIFTY CE: OPEN gives waiting; COMPLETE with filled 65 but no trades gives reconciliation_required; COMPLETE with trades 65 gives filled; basket closed (no tag) gives nothing_placed; an unknown status word gives waiting.
attack: every intended order submitted while the broker still shows 3 legs: IN_PROGRESS; positions show all 4 legs and the broker says EXECUTED but the book never recorded the 4th fill: RECONCILIATION_REQUIRED; Kite COMPLETE 65 with no matching trades: reconciliation_required. None reached complete/filled from submission alone

GC-3 P0 item 7: re-verification on main of criteria whose evidence predated fingerprints.
Recorded by the orchestrator from the verifier's returned block.
