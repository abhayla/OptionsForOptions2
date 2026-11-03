---
work_item: W-212
requirement: REQ-168
ac: AC-5
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "43e139d6577d"
commands: "python (inline) registry check: the 15 adjustments.* keys all in group 'Adjustment defaults' and equal to prefs_mod.KEYS; read user_preferences_store.answers, settings_store.settings_in_force, background.py rebuild()"
---
answers() uses the admin value in force when the user has no row or a NULL reset row and the user's own value when set; the worker's rebuild calls values_for(user) every 30 s, so an admin change reaches default-following users within one rebuild. Attack: a user's own value is kept (source 'yours'); an admin value the registry refuses fails closed with an error, not a silent default.

Code reading only. DB proof owed: tests_app/test_user_preferences.py::test_core_proof_..., ::test_a_users_own_value_is_kept_when_the_admin_default_changes.

Recorded by the orchestrator from the verifier's returned block.
