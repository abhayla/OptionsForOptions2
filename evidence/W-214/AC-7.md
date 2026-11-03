---
work_item: W-214
requirement: REQ-170
ac: AC-7
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "ade50e3f9933"
commands: "python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_background_settings_cache.py tests_app/test_background_cycle.py; read background.py cycle(), _check_unpaused(), _evaluate_and_gate(), rebuild()"
---
81 passed. Every cycle re-resolves settings (_settings_safely, background.py:1294-1300) and speed; the preset is built per check from live values (line 1139); user values re-read every 30 s; nothing frozen at start-up; a missing key pauses the strategy rather than defaulting.

Admin changes apply within settings_cache.LAG_SECONDS; _close_pass reuses the last check's preset until the next check.
