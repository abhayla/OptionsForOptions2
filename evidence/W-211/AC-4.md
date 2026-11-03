---
work_item: W-211
requirement: REQ-167
ac: AC-4
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "752e47b6cefb"
commands: "python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_background_settings_cache.py tests_app/test_background_cycle.py; read backend/ofo_app/settings_cache.py and background.py; read tests/test_settings_reader_guard.py"
---
81 passed. The cache polls every 2 s, LAG_SECONDS 5, measured; the cycle resolves settings from memory with no restart; a future-dated row applies at its time. Not proven: one test per wired setting (wiring files are DB-only, not run). Typed values on the iron condor path that are not settings: backend/ofo/adjustment/carry.py:29 CARRY_GAP_PCT = Decimal(2), backend/ofo_app/adjustment_check.py:76, backend/ofo_app/background.py:154 MARGIN_REFRESH_S = 300.

Per-setting wiring DB proof owed: tests_app/test_settings_*_wiring.py, test_settings_tick_rate.py.

Recorded by the orchestrator from the verifier's returned block.
