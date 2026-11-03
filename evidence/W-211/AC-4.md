---
work_item: W-211
requirement: REQ-167
ac: AC-4
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "752e47b6cefb"
commands: "python -m pytest -q -p no:cacheprovider tests/test_settings_literal_guard.py tests/test_settings_reader_guard.py tests/test_settings_registry.py; AST literal scan of backend/ofo/adjustment/*.py, ofo_app/adjustment_check.py, ofo_app/background.py; grep carry_gap_percent backend; read ADR-240 (3), registry.json"
---
71 passed. carry_gap_percent is wired (calc.py:117, outcome.py:257, background.py:360) and the carry.py literal is gone. Still typed on the playbook path: playbook_eval.py:995 S02_NET_DELTA_PER_LOT = Decimal('0.15') and :996 S12_PCT_OF_MAX_PROFIT = Decimal(40); neither has a registry key nor a KNOWN_LEFTOVERS row, so the guard does not see them, and both decide whether a user-visible record opens (ADR-240 (3)).

Mapping each wired setting to a test not finished; whether carry_gap_percent has a wiring test is unverified.

Recorded by the orchestrator from the verifier's returned block.
