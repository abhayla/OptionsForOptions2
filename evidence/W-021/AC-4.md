---
work_item: W-021
ac: AC-4
requirement: REQ-060
ac_fp: "b4eafbc50bb9"
result: fail
verified_by: "verifier (opus, fresh context, GC-3 P0 item 7, main 85e38e0, 2026-10-17)"
builder: "builders (W-021, W-037, W-085; live path W-095, W-096)"
date: '2026-10-17'
commands: "python -m pytest -q -p no:cacheprovider tests/reconciliation/test_external_change.py tests/reconciliation/test_resolution.py tests/reconciliation/test_blocking.py (44 passed); scratch attack.py, ev.py; grep backend/ofo_app for ofo.reconciliation, record_report, reconciliation_required"
---

AC: AC-4
result: fail
commands: python -m pytest -q -p no:cacheprovider tests/reconciliation/test_external_change.py tests/reconciliation/test_resolution.py tests/reconciliation/test_blocking.py (44 passed); scratch attack.py, ev.py; grep backend/ofo_app for ofo.reconciliation, record_report, reconciliation_required
observed: Domain: a buyback of 25 in Kite gives EXTERNAL_MODIFICATION, the audit event EXTERNAL_BROKER_CHANGE_DETECTED and the Reconciliation Required flag. Live: backend/ofo_app never imports ofo.reconciliation.compare or resolution (execute_plan.py:15-17); execute.py:475-486 recomputes a block per request, writes no audit event and no Reconciliation Required state.
attack: ep.strategy_blocked({K:150},{K:75}) is False and ({K:-100},{K:-75}) is False: a position added in Kite on the strategy's own contract is not detected; a buyback is refused for that one request only and never recorded

GC-3 P0 item 7: re-verification on main of criteria whose evidence predated fingerprints.
Recorded by the orchestrator from the verifier's returned block.
