---
work_item: W-140
ac: AC-1
requirement: REQ-072
ac_fp: "cbc9e9db983e"
result: pass
verified_by: "independent verifiers (Opus, fresh context; start check on f9a8d780, DB part Sonnet on fb9a3702, round 2 on fix d76cd0e0)"
builder: "builders (earlier work items; builder sequence row 12 fix 1, Sonnet)"
date: '2026-10-23'
commands: "start check (Opus, fresh) on f9a8d780, results-rows-12-14.md; DB part (Sonnet) on fb9a3702: 224 passed"
---

AC: AC-1
result: pass
commands: start check (Opus, fresh) on f9a8d780, results-rows-12-14.md; DB part (Sonnet) on fb9a3702: 224 passed
observed: index ids NSE_INDEX:1001 / BSE_INDEX:1 (parser.py ZERODHA_INDEX_SEGMENT, models.py:39-40); a SENSEX leg in a NIFTY strategy refused, naming SENSEX; the NSE cash row sharing token 1001 handled
attack: see results-rows-12-14.md (rows 12-14 start check: hand computations, 24 mutants)

Recorded by the orchestrator from the verifier's returned block.
