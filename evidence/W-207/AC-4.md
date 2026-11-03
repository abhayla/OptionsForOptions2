---
work_item: W-207
requirement: REQ-160
ac: AC-4
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "a7ebb73b1ca3"
commands: "read explanations.py:1845-1850; grep -rn playbook_test_past_out_of_v1 backend/ofo_app frontend/src; npx vitest run tests/adjustments-page.test.js"
---
playbook_test_past_out_of_v1 reads 'Testing against past expiries is not in this version: it needs licensed historical option data.' (explanations.py:1847-1849), returned as past_note by both playbook routes (routes/playbooks.py:289, 541) and shown at pb-past-note (AdjustmentsPage.vue:~136). vitest 33 passed. Attack: 'not in this version' instead of 'V1' - same meaning, plainer.

Plain wording accepted.

Recorded by the orchestrator from the verifier's returned block.
