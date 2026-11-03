---
work_item: W-206
requirement: REQ-159
ac: AC-3
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "0798a169d6a7"
commands: "python -m pytest -q -p no:cacheprovider tests/adjustment (723 passed); read playbook_eval.py:560-583 (_rule); grep tests test_all_of_rule (line 333), test_any_of_rule_fires_when_one_member_fires (line 348)"
---
Not verified in budget (no combined-rule attack run). Code read: all_of fires only if all members fire and one NotChecked member makes the rule NotChecked; any_of fires on any member, else NotChecked if a member is missing, else clear; the editor offers an AND/OR flip (AdjustmentsPage.vue ~97). Leaning PASS.

Re-run with an all_of [T-01, T-03] snippet with one member data-unavailable.

Recorded by the orchestrator from the verifier's returned block.
