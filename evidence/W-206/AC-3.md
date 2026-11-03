---
work_item: W-206
requirement: REQ-159
ac: AC-3
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 3)"
date: 2026-11-03
ac_fp: "0798a169d6a7"
commands: "python <scratchpad>/atk1.py (rules built on the ADJ-01 body from tests/adjustment/test_playbook_eval.py, evaluate called); env -u TEST_DATABASE_URL -u TEST_ADMIN_DATABASE_URL -u ALEMBIC_DATABASE_URL python -m pytest -q -p no:cacheprovider tests/adjustment/test_playbook_eval.py -k 'all_of or any_of or rule'"
---
all_of [T-01 fires, T-11 unavailable] -> NotChecked (T-11), never a Flag; all_of [T-01, T-03] with T-03 delta None -> NotChecked (T-03); any_of with one member firing and another unavailable -> Flag (T-01); any_of with nothing fired and one unavailable -> NotChecked; all_of with both available and one not firing -> no result. 2 tests passed; code read playbook_eval.py _rule 564-583.

all_of with one false and one unavailable member gives NotChecked, not false: conservative, does not break the AC.

Recorded by the orchestrator from the verifier's returned block.
