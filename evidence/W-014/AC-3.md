---
work_item: W-014
ac: AC-3
result: pass
verified_by: "verifier (opus, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/execution/test_validation.py; inline attacks"
---

AC: AC-3
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/execution/test_validation.py; inline attacks
observed: 17 passed; unknown eligibility blocks all 4 legs; duplicate leg (same and opposite side) -> DUPLICATE_LEG; empty data_health -> DATA_UNHEALTHY; expired expiry -> EXPIRY_PASSED; BANKNIFTY -> UNDERLYING_UNSUPPORTED; qty 64 -> QUANTITY_INVALID; max_loss Decimal 7085.00 for 1-lot condor; float margin refused
attack: empty data map, one stale input, margin one paisa short, opposite-side duplicate, float money injection: all rejected or blocked

Recorded by the orchestrator from the verifier's returned block.
