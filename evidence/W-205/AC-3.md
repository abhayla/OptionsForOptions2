---
work_item: W-205
requirement: REQ-158
ac: AC-3
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 4)"
date: 2026-11-04
ac_fp: "21a5018bd134"
commands: "read backend/ofo_app/playbook_store.py:196-206,408-414,462-531; read backend/ofo_app/alembic/versions/0031_adjustment_playbooks.py:394; read backend/ofo/errors/templates.py:1275-1280; read tests_app/test_playbook_routes.py:131-157, tests_app/test_playbook_store.py:101-142; python -m pytest -q -p no:cacheprovider tests/errors/test_user_text_slot.py"
---
Create, duplicate (via create, :481) and rename (:497) all go through _write_named; a case-insensitive, whitespace-folded clash per user and type is refused with the template text; delete works; test_user_text_slot 10/10. Gap: _NAME_USED (:201-202) filters user_ref = :user_ref and the index (0031:394) uses coalesce(user_ref,''), so a user can create, duplicate or rename to the system playbook's own name ('Iron condor: system default') and two same-named playbooks show in one type, against 'a name is unique within a type'. No test covers it.

If 'unique among the user's own' is intended, the AC needs to say so.

Recorded by the orchestrator from the verifier's returned block.
