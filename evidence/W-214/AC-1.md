---
work_item: W-214
requirement: REQ-170
ac: AC-1
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "6cce2bb019f4"
commands: "python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_background_settings_cache.py tests_app/test_background_cycle.py; python -m pytest -q -p no:cacheprovider tests/adjustment/test_alert_gate.py tests/adjustment/test_alert_gate_lapse_restore.py tests/adjustment/test_alert_presets.py tests/adjustment/test_gate_readings.py; python -I attack script against backend/ofo/adjustment/alert_gate.py"
---
81 + 100 passed. Own sequences: T-07 'ge 80' wobbling 81/79 every 10 s for 30 min opened exactly 1 record; a cross at 10:38:30 checked at 10:38:40 opened nothing; a spike that returns before the close opened nothing; the same cross opened at the 10:39 close. The screen check writes none (routes/adjustment_check.py:8,174).

Per-record DB writes not exercised (tests_app/test_background_worker.py).
