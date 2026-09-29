---
work_item: W-034
ac: AC-2
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/table/test_total_row.py; python -m pytest -q -p no:cacheprovider tests/table; python -m pytest -q -p no:cacheprovider; ad-hoc python -c build_table attacks"
---

AC: AC-2
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/table/test_total_row.py; python -m pytest -q -p no:cacheprovider tests/table; python -m pytest -q -p no:cacheprovider; ad-hoc python -c build_table attacks
observed: 12 passed; 42 passed; 1285 passed. Golden TOTAL: P&L % +16.7%, Entry Value 6825.00 Cr (hand-recomputed 1365/8175=16.697, 91x75=6825). Dr spread 4500 Dr; mixed qty 12000 Cr; zero net 0.00 with side None; long-call tie 16.65 -> 16.7 and -16.65 -> -16.7
attack: Futures: BUY FUT + PE gives Entry '—' and % 2.9; SELL FUT (+ long put) gives Entry '—' and % '—' (max loss unlimited); unlimited-loss naked short gives '—' with Entry 6862.50 Cr; zero max loss and missing LTP give '—'; calendar spread gives '—' (MultiExpiryError confirmed in engine/metrics.py); break-even long call at LTP=entry gives +0.0%; debit spread with LTPs gives 375/4500 = +8.3%; all money cells are Decimal; empty legs raises ValueError upstream. Notes: work/W-034.md said Entry Value 19,800 (stale, pre-Q236; corrected by the orchestrator, class 1); multi-expiry '—' not literally in the spec text (clarification added to REQ-035).

Recorded by the orchestrator from the verifier's returned block.
