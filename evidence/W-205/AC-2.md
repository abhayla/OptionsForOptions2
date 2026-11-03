---
work_item: W-205
requirement: REQ-158
ac: AC-2
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "ee075128f8e1"
commands: "python json load backend/ofo/adjustment/system_playbooks.json; read backend/ofo_app/routes/playbooks.py:201-206; read backend/ofo_app/adjustment_check.py:131-138; read backend/ofo_app/routes/adjustment_check.py:229-232"
---
Seed status is correct (ic approved, 11 draft) and the playbooks routes label Draft for system playbooks only (routes/playbooks.py:205). But adjustment_check.resolve (adjustment_check.py:138) passes pb.status through for a user's own active playbook; that column defaults to 'draft', so GET adjustment check returns playbook.draft=true for a user's own copy, even of the approved iron condor (routes/adjustment_check.py:232). 'Every screen' not verified in budget.

Fix: draft only if is_system and status=='draft'. No frontend consumer of check.playbook.draft found by grep, so visible impact unconfirmed.

Recorded by the orchestrator from the verifier's returned block.
