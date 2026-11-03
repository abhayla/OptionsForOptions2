---
work_item: W-212
requirement: REQ-168
ac: AC-4
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "b5183986dc33"
commands: "read ofo/adjustment/compare.py:552-580, routes/adjustment.py:590, routes/tracking.py:288-296, background.py:700-725,1042-1087; grep -rn gap_after_open|checked only until"
---
backend/ofo/errors/templates.py:1220 _trig('gap_after_open', 138, 'The gap at the open is checked only until 09:30.') hard-codes 09:30 with no slot, while playbook_eval.py:479 raises it using the user's gap_until preference (range 09:15-15:30): a user who sets 10:00 gets a line naming 09:30, so the line does not name the value it used. Passing parts: near-level lines name the threshold; compare reads range, steps and moves() (compare.py:552-580); the worker re-reads preferences every 30 s; no code path writes saved plans.

Fix: a {gap_until} slot in gap_after_open, filled from the preference. DB proof owed: tests_app/test_user_preferences.py core proof (plan digest unchanged).

Recorded by the orchestrator from the verifier's returned block.
