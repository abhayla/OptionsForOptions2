---
work_item: W-001
ac: AC-1
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/engine/test_formulas.py; python - (heredoc attack script)"
---

AC: AC-1
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/engine/test_formulas.py; python - (heredoc attack script)
observed: 18 passed; sign matrix mismatches 0 across BUY/SELL x CE/PE/FUT at 22900/23000/23100 vs independent Fraction reference, entry 87.35, qty 65; all results type Decimal
attack: sign at below/at/above strike for 6 leg types: 0 mismatches. qty 0/-75/75.0, float strike/entry/ltp, strike -5/Infinity, datetime expiry, market -1, int market: all rejected with ValueError. Decimal(0.1) entry gets through (-0.3000000000000000166533453693): gap routed to W-002 (REQ-032 AC-4), not a formula error

Recorded by the orchestrator from the verifier's returned block.
