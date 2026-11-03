---
work_item: W-212
requirement: REQ-168
ac: AC-3
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "61a9d86414c1"
commands: "grep -rn user_adjustment_preferences|user_preferences_store|set_preference|reset_preference backend (*.py); read tests_app/test_user_preferences.py lines 122-160"
---
Only routes/adjustment_preferences.py writes the table (through the store); all three routes and the get_user_preferences dependency depend on require_user (current_user_ref); every store query takes :user and _user() rejects an empty or non-string ref. Attack: no second writer found by grep; the guard-coverage test fails if a route lacks the guard.

DB proof owed: tests_app/test_user_preferences.py::test_isolation_a_write_by_user_a_never_changes_user_b, ::test_isolation_over_http_the_guard_decides_whose_row_is_written, ::test_every_preference_route_and_the_read_dependency_depend_on_the_one_guard.

Recorded by the orchestrator from the verifier's returned block.
