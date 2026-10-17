---
work_item: W-021
ac: AC-7
requirement: REQ-060
ac_fp: "ebd7a963df8f"
result: fail
verified_by: "verifier (opus, fresh context, GC-3 P0 item 7, main 85e38e0, 2026-10-17)"
builder: "builders (W-021, W-037, W-085; live path W-095, W-096)"
date: '2026-10-17'
commands: "python -m pytest -q -p no:cacheprovider tests/reconciliation/test_standalone.py (10 passed); scratch attack.py"
---

AC: AC-7
result: fail
commands: python -m pytest -q -p no:cacheprovider tests/reconciliation/test_standalone.py (10 passed); scratch attack.py
observed: Domain: the REQ example SELL CE x50 + standalone x25: broker -75 blocks no one, broker -50 is QUANTITY_MISMATCH blocking only X. The live app has no standalone input (0 hits outside a docstring): strategy_blocked({K:-50},{K:-50}) is False; a surplus on a held contract counts as 'in no strategy' live but QUANTITY_MISMATCH in the domain, two readings of AC-7 on main. No fresh AC-7 evidence existed (W-021/AC-7.md was unpinned).
attack: ran the REQ's own example through both layers; the shared-contract case from AC-6 also breaks 'blocks only the strategy whose contract quantity disagrees'

GC-3 P0 item 7: re-verification on main of criteria whose evidence predated fingerprints.
Recorded by the orchestrator from the verifier's returned block.
