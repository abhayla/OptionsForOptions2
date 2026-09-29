---
work_item: W-023
ac: AC-1
result: pass
verified_by: "verifier (opus, fresh context, rounds 3-4) and verifier (sonnet, mutation checks W-023e/W-023f)"
builder: "builder (opus); rounds 4-6 tests by builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/execution/test_partial.py; independent hand computation (round-3 and round-4 verifiers)"
---

AC: AC-1
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/execution/test_partial.py; independent hand computation (round-3 and round-4 verifiers)
observed: golden Iron Condor with the 23,600 CE buy rejected -> PARTIAL_EXCEPTION; engine metrics from the broker's 3 real legs: max profit 8,775.00 (135 x 65), max loss UNLIMITED, breakevens 22,865 / 23,535, live P&L -1625.00, all Decimal
attack: broker position 2x lot on a leg and a broker order unknown to the book -> RECONCILIATION_REQUIRED, no metrics trusted

Recorded by the orchestrator from the verifier's returned block.
