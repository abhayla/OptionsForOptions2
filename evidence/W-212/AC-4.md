---
work_item: W-212
requirement: REQ-168
ac: AC-4
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 3)"
date: 2026-11-03
ac_fp: "b5183986dc33"
commands: "python -m pytest -q -p no:cacheprovider tests/adjustment/test_situation_rules.py tests/errors; read templates.py:1220, playbook_eval.py:480-486, routes/adjustment_check.py:155"
---
746 passed. gap_after_open reads 'checked only until {until}.' with a ClockTime slot; playbook_eval._t13 raises it with until=c.gap_until and the check route renders the slots; test_the_gap_after_open_line_names_the_preference runs 09:30, 10:00 and 15:30. Attack: a 10:00 preference reads 'until 10:00.' and the test asserts 09:30 is absent; the worker and both check routes pass prefs.gap_until.

Round-2 FAIL fixed in ef8ed5e5.

Recorded by the orchestrator from the verifier's returned block.
