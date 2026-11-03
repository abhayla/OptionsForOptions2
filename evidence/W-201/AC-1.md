---
work_item: W-201
requirement: REQ-112
ac: AC-1
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "d89803c9a39b"
commands: "grep -rn open_suggestion backend --include=*.py; sed -n 395,445p backend/ofo_app/alembic/versions/0031_adjustment_playbooks.py; grep -rn rules.actions backend --include=*.py"
---
The unique open index (strategy_id, rule_id) is in 0031 (~442). open_suggestion (playbook_store.py:577) has one caller, background.py:602 (alert gate: user-rule and playbook flags). The REQ-042 prepared exit is built by backend/ofo/rules/actions.py:49 respond(), which nothing in backend/ofo_app imports; no suggestion record is created for it. Attack: no prepared-exit-to-suggestion link found.

The AC's third source has no record path. DB proof owed for the other two: tests_app/test_playbook_store.py (open_suggestion tests).

Recorded by the orchestrator from the verifier's returned block.
