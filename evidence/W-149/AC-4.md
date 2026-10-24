---
work_item: W-149
ac: AC-4
requirement: REQ-077
ac_fp: "8dd44cb872ed"
result: pass
verified_by: "independent verifiers (Opus part checks 21m/21b/21a/21d with round 2; Sonnet 21c check + round 2; Opus CI-fix check + round 2; Opus row 21 closing check on 9730cda2)"
builder: "builders (Opus: 21m 8a3bf0d2, 21b 8f5dc56e, 21a c851c84d, 21d 6d4ae53f; Sonnet: 21c f1a5e938 + fix 264576bb, CI fix 6bac88cf..ab38cd8d)"
date: '2026-10-24'
commands: "vitest and app runs as above; mutant M9 strategies.py:251 entry_source forced 'captured'; M10 strategies.py:292 drop leg.entry_source; gh run view 40063948683 --log (CI on 9730cda2: 3854 passed, 6 skipped)"
---

AC: AC-4
result: pass
commands: vitest and app runs as above; mutant M9 strategies.py:251 entry_source forced 'captured'; M10 strategies.py:292 drop leg.entry_source; gh run view 40063948683 --log (CI on 9730cda2: 3854 passed, 6 skipped)
observed: Save: strategies.py:292 passes entry_source into the stored form; :295-296 refuses entry_source without the entry pair (migration 0024 allows the ninth key). Open: :251 entry_source from the stored entry. Frontend (21c): typed leg saved with entry_source 'typed', reopened as typed.
attack: M9: 1 failed (test_ac_4_ac_7_reopening_returns_exactly_the_saved_entries_marks_and_times_and_invents_none). M10 not runnable locally (ofo_test INTERNAL_SYSTEM_002); by reading, the CI database test asserts stored_legs[0]['entry_source']=='typed' (lines 423-426) - unverified locally, green in CI.

Recorded by the orchestrator from the verifier's returned block.
