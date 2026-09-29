---
work_item: W-026
ac: AC-1
result: pass
verified_by: "verifier (opus, fresh context; round 3 W-026c against the independent review's bar)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/execution/test_strategy_only.py tests/execution/test_strategy_guard.py tests/orders tests/strategy tests/execution; mutant M13 (OrderBook.add version check removed)"
---

AC: AC-1
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/execution/test_strategy_only.py tests/execution/test_strategy_guard.py tests/orders tests/strategy tests/execution; mutant M13 (OrderBook.add version check removed)
observed: 289 passed; Order refuses a missing or malformed strategy id or version; OrderBook.add refuses v99, an unbound strategy, v0 and '1'; transition_key refused; M13 killed
attack: round 2 failed: OrderBook.add accepted v99 and S-UNBOUND. Round 3: an order for v2 (not in the record) and an S-2 order on the S-1 sink both refused

Recorded by the orchestrator from the verifier's returned block.
