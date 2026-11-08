---
work_item: W-205
requirement: REQ-158
ac: AC-2
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "ee075128f8e1"
commands: "grep -rn draft backend/ofo_app (routes, adjustment_check.py); python (read system_playbooks.json statuses); python -m pytest -q -p no:cacheprovider tests/adjustment/test_system_playbooks_seed.py tests/errors/test_user_text_slot.py tests/adjustment/test_registry.py; npx vitest run tests/adjustments-page.test.js"
---
After the round-1 fix (b84b5b3c) draft is derived as is_system and status=='draft' in adjustment_check.py:91, routes/playbooks.py:205 and routes/adjustment_plan.py:224; seed ic approved, the other 11 draft; the page shows Draft only from the server flag. pytest 27, vitest 33 incl. 'Draft shows only on a draft system playbook'. Attack: an own copy (status default 'draft') now gets draft=False.

Residual: a plan copied from a draft system playbook carries draft=False (adjustment_check.py:138); not checked whether a screen shows such a plan's numbers.

Recorded by the orchestrator from the verifier's returned block.
