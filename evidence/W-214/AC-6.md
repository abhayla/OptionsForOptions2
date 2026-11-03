---
work_item: W-214
requirement: REQ-170
ac: AC-6
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "ed9eb7389bd4"
commands: "read backend/ofo/adjustment/alert_presets.py; registry.json defaults dump; grep user_preferences_store.py"
---
preset_for (alert_presets.py:94-105) takes re-arm only from admin settings and the cap as min(user, admin ceiling); candle, cool-down and quiet time from the user's values; USER_KEYS excludes re-arm and speed; check speed via speeds.background_check_seconds.<style>; user_preferences_store.py:176-179 refuses a cap above the ceiling; style from the pin, else days left and expiry kind. Registry defaults match the preset table.

Frontend vitest not run; DB proof of the cap refusal owed.

Recorded by the orchestrator from the verifier's returned block.
