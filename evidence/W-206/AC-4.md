---
work_item: W-206
requirement: REQ-159
ac: AC-4
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "a189106cf019"
commands: "grep ACTING_DAY_PAIRS|NotChecked|_tighten backend; read playbook_eval.py 794-812, routes/playbooks.py:293, playbookEditor.js:64-69, AdjustmentsPage.vue:114"
---
Not verified in budget. Seen after the round-1 fix (ca2ee383): ACTING_DAY_PAIRS (playbook_eval.py:909); day_answers answers NotChecked(DAY_RULE_NOT_CHECKED) for non-acting pairs (:812); the labels route sends day_acting (routes/playbooks.py:293); the editor greys such rows (AdjustmentsPage.vue:114). Not checked: the table contents, _tighten (adjustment_check.py:150) limited to listed pairs, every switched-on ic rule acting, the plan sheet, the carry_gap_percent default.

tests/adjustment/test_day_rules_not_checked.py passed within the 723 but was not read.

Recorded by the orchestrator from the verifier's returned block.
