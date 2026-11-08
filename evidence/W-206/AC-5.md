---
work_item: W-206
requirement: REQ-159
ac: AC-5
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 4)"
date: 2026-11-04
ac_fp: "5f691e249ef6"
commands: "env -u TEST_DATABASE_URL -u TEST_ADMIN_DATABASE_URL -u ALEMBIC_DATABASE_URL python -m pytest -q -p no:cacheprovider tests/adjustment/test_situation_rules.py; read backend/ofo/adjustment/playbook_eval.py:980-1082; read spec/decisions/ADR-240.md; python listing the situation ids in backend/ofo/adjustment/system_playbooks.json; grep S-08|S-09 backend frontend/src spec"
---
36 passed. S-02 and S-12 are rules (playbook_eval.py:1032-1082), S-03/S-04/S-05 guidance (:992), labels reach the editor via situation_kinds; no 'best/recommend' in the possible-approaches text. FAIL: the AC says S-01 to S-12, but the IC system playbook lists only S-01..S-07, S-10, S-11, S-12; S-08 (day before a known event) and S-09 (weekend or holiday) are absent, ADR-240 never classifies them, and situation_kind (playbook_eval.py:995-996) answers 'rule' for anything not in the guidance tuple although S-08 has no checker (no event list, explanations.py:308).

Fix: add S-08/S-09 with Guidance labels (ADR-240 amendment) or amend the AC to the 10 situations.

Recorded by the orchestrator from the verifier's returned block.
