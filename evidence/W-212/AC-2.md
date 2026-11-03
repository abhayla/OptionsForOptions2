---
work_item: W-212
requirement: REQ-168
ac: AC-2
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "00ea1d9d25ac"
commands: "read backend/ofo_app/user_preferences_store.py, routes/adjustment_preferences.py, alembic 0033, tests_app/test_user_preferences.py (read only); python (inline) ofo.settings.validate on out-of-range, NaN, non-integer, time 960 and JSON-number inputs; python -m pytest -q -p no:cacheprovider tests/adjustment/test_approach_compare.py tests/adjustment/test_detection.py tests/test_settings_registry.py (57 passed)"
---
set_preference calls registry validate before insert. Observed refusals with reasons: near_level 9 -> 'must be between 0.1 and 5 (percent)', NaN, steps 48.5, time 960, a JSON number 0.5, delta 30 -> 'enter 0.3'. GET returns value, source (yours/default), admin_default and history; reset inserts a NULL row and the migration trigger refuses UPDATE and DELETE, so history is kept. Attack: bad values are refused before any write.

DB proof owed: tests_app/test_user_preferences.py::test_a_refused_value_answers_the_reason_and_writes_nothing, ::test_core_proof_user_value_then_reset_then_admin_default_moves_the_reset_user.

Recorded by the orchestrator from the verifier's returned block.
