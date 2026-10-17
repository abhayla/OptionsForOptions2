---
work_item: W-023
ac: AC-1
requirement: REQ-058
ac_fp: "16cf37e939af"
result: fail
verified_by: "verifier (opus, fresh context, GC-3 P0 item 7, main 85e38e0, 2026-10-17)"
builder: "builders (W-023, W-028, W-036, W-043)"
date: '2026-10-17'
commands: "python -m pytest -q -p no:cacheprovider tests/execution/test_partial.py (8 passed); scratch verify-req058a/attack.py, attack_domain.py; grep backend/ofo_app for ofo.execution.partial"
---

AC: AC-1
result: fail
commands: python -m pytest -q -p no:cacheprovider tests/execution/test_partial.py (8 passed); scratch verify-req058a/attack.py, attack_domain.py; grep backend/ofo_app for ofo.execution.partial
observed: The domain ofo.execution.partial.assess gives PARTIAL_EXCEPTION and recomputes metrics, live P&L and margin from the broker's legs. No file under backend/ofo_app imports it (0 hits). The live path gives only plan state 'partial' and per-contract units; ReturnOut has no risk, live P&L or margin field; realised_pnl is None while held; ReturnCheck.vue shows the state word, units and realised P&L only.
attack: COMPLETE 65 + CANCELLED 0 gives live 'partial' (the exception state exists) but no risk, P&L or margin is recalculated or shown for the held partial

GC-3 P0 item 7: re-verification on main of criteria whose evidence predated fingerprints.
Recorded by the orchestrator from the verifier's returned block.
