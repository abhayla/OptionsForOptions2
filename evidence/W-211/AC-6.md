---
work_item: W-211
requirement: REQ-167
ac: AC-6
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "41ed6542b33b"
commands: "python -m pytest -q -p no:cacheprovider tests/test_settings_literal_guard.py tests/test_settings_reader_guard.py; read both files in full"
---
Passed. test_every_registry_key_has_a_reader scans backend/ and frontend/src for each key; test_no_old_literal_is_back_in_its_old_home checks old homes by name and exact literal, fails closed on unparsable files and checks retired env reads; self-tests prove it fails on a redefined constant, a renamed constant with the same literal, a key with no reader and an unresolvable source. Attack: the guard covers only modules in OLD_HOMES; CARRY_GAP_PCT, MARGIN_REFRESH_S and the timeutil hours sit outside it.

Fits the AC wording (wired modules), not the broader ADR-222 (1).

Recorded by the orchestrator from the verifier's returned block.
