---
work_item: W-201
requirement: REQ-112
ac: AC-7
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "91498a496c40"
commands: "python -m pytest -q -p no:cacheprovider tests/adjustment/test_alert_gate.py tests/adjustment/test_alert_gate_lapse_restore.py tests/adjustment/test_alert_texts.py; read backend/ofo/adjustment/alert_gate.py (_refresh, _decide, step, dismiss, restore); read background.py _load_gates"
---
65 passed. A dismissed record sets 'cleared' on a safe-by-band close with no Lapsed event and reopens only when armed (cleared and cool-down passed). A None reading neither clears nor reopens (test_none_never_clears). A higher ladder level opens at once with worse='dismissed' ('Worse than the one you dismissed'). Attack: restore() marks all rules not-cleared, so after a restart it can only stay quiet longer.

DB proof owed: tests_app/test_alert_gate_storage.py, tests_app/test_background_worker.py.

Recorded by the orchestrator from the verifier's returned block.
