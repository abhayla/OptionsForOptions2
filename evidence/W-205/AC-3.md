---
work_item: W-205
requirement: REQ-158
ac: AC-3
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 5)"
date: 2026-11-04
ac_fp: "21a5018bd134"
commands: "env -u TEST_DATABASE_URL -u TEST_ADMIN_DATABASE_URL -u ALEMBIC_DATABASE_URL python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_playbook_store.py; read playbook_store.py:202-204, _name 410-416, _write_named 463-476, create/duplicate/rename 479-500; read alembic 0031 seed and index adjustment_playbooks_name"
---
_NAME_USED now matches (user_ref = :user_ref OR is_system) AND strategy_type = :type AND lower(name) = lower(:name) AND id IS DISTINCT FROM :id; _name() trims and folds whitespace first, so case/whitespace variants of 'Iron condor: system default' hit the system row; create, duplicate (via create) and rename all go through _write_named; another type's system name is not matched (type filter); the refusal is built by _taken from the typed name and the type.

DB proof owed: tests_app/test_playbook_store.py::test_req158_ac3_the_system_playbooks_name_is_taken_for_create_duplicate_and_rename (builder's db_run_fresh run: 47 passed; read, not run here).

Recorded by the orchestrator from the verifier's returned block.
