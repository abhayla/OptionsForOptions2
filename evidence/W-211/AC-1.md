---
work_item: W-211
requirement: REQ-167
ac: AC-1
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "d7144db420e5"
commands: "git rev-parse HEAD (989623c9); python -m pytest -q -p no:cacheprovider tests/test_settings_registry.py tests/test_settings_literal_guard.py tests/test_settings_reader_guard.py tests/test_settings_times.py tests/test_settings_batch2_pure.py tests/outcome/test_settings_wiring.py tests/strategy/test_settings_value.py tests/entitlements/test_settings_days.py tests/marketdata/test_feed_windows_settings.py tests/marketdata/test_forward_quality_settings.py; read backend/ofo/settings/__init__.py, backend/ofo_app/settings_store.py, migration 0032"
---
232 passed. registry.json has 92 entries; the loader rejects a missing key, group, label, unit, type, range, default or what_it_changes, floats, duplicates and a default outside its range. The store reads the newest row with effective_from <= at via DISTINCT ON, else the default; migration 0032 has an append-only guard. Attack: a stored row the registry refuses raises SettingsError instead of silently using the default.

DB proof owed: tests_app/test_settings_store.py.

Recorded by the orchestrator from the verifier's returned block.
