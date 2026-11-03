---
work_item: W-206
requirement: REQ-159
ac: AC-4
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 3)"
date: 2026-11-03
ac_fp: "a189106cf019"
commands: "python <scratchpad>/atk2.py (all 12 system playbooks plus malformed day rules through day_answers); env -u TEST_DATABASE_URL -u TEST_ADMIN_DATABASE_URL -u ALEMBIC_DATABASE_URL python -m pytest -q -p no:cacheprovider tests/adjustment/test_day_rules_not_checked.py; env -u TEST_DATABASE_URL python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_day_rules_labels.py; cd frontend && npx vitest run tests/day-rule-not-checked.test.js"
---
ACTING_DAY_PAIRS = {expiry/5, expiry/4, beforeWeekend/0, beforeHoliday/0}; every switched-on day rule in all 12 system playbooks is in it. Attack: action True, action '5', beforeHoliday with action 5 or 4 -> NotChecked (adjust_trigger_day_rule_not_checked); an off rule -> no answer; _tighten requires day_rule_acts; the labels route sends day_acting (routes/playbooks.py:293); the editor greys via dayRuleNotChecked. Tests 16, 2 and 3 passed; carry_gap_percent default 2.

The plan sheet shows no day rule at all, so its part holds trivially; the carry_gap_percent readers were read by grep only.

Recorded by the orchestrator from the verifier's returned block.
