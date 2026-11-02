---
work_item: W-158
ac: AC-1
result: fail
verified_by: "orchestrator live run (GC-LIVE3, owner's Kite session), not an independent verifier"
builder: "n/a (live check of feature/adjustments @ dd403d80)"
date: '2026-11-02'
commands: "python D:/Abhay/scratch/gclive3/probe/c1.py (POST /api/strategies/leg-edit on the dev API, inprocess mode, LIVE_MARKET=1)"
---

AC: AC-1 (REQ-078: Shift, Width, Hedge core proof)
result: fail (strikes and max loss pass; latency fails)
commands: python D:/Abhay/scratch/gclive3/probe/c1.py, run 2026-11-02 11:11:36 IST, NIFTY 2026-11-09, spot 23337.60
observed:
- base iron condor from real listed strikes, typed at the live last prices: BUY 22900 PE @ 61.20, SELL 23000 PE @ 80.00, SELL 23500 CE @ 126.45, BUY 23600 CE @ 90.15 (1 lot, 65)
- Shift +1 -> PE 22950 / 23050, CE 23550 / 23650: matches AC-3 (every option leg +50); all four in the day's strike list
- Width +1 -> PE 22850 / 22950, CE 23550 / 23650: matches AC-4 (calls up one step, puts down one step); all listed
- Hedge +1 -> PE 22850 / 23000, CE 23500 / 23650: matches AC-5 (equal hedges, both move out one step); all listed
- max loss by hand, base: net credit 55.10 x 65 = max profit 3,581.50; max loss (100 - 55.10) x 65 = 2,918.50. Engine: max loss 3,209.64, max profit 3,290.36, charges 291.14. 2,918.50 + 291.14 = 3,209.64 and 3,581.50 - 291.14 = 3,290.36: equal to the paisa (the engine's max figures include charges)
- after each move the engine-minus-hand gap is 289.08 / 283.42 / 287.80 (charges follow the premiums); the per-move charges were not captured, so these three are NOT checked to the paisa
- 50 consecutive edits (Shift +1 / -1 alternating): min 3,093 ms, median 4,276 ms, p95 4,783 ms, max 5,709 ms -> FAIL against p95 <= 1,000 ms
attack: n/a (live core proof)
notes:
- the dev API's every database round trip costs about 0.7 s from this PC (GET /health = one SELECT 1: 0.51-1.37 s on 10/10 calls; ping to the DB host 12 ms; a no-DB route 12 ms), measured 10:07-10:10 the same day; the leg-edit reply waits on it. Same class as #636 (knowledge/findings/check-latency-bound-by-db-round-trips.json). Not re-planned today.
- the paper book shows max profit / max loss without charges (strategy 78: 3,458 / 3,042) while the builder, Compare and Live Strategies show them with charges (3,168.79 / 3,331.21): one strategy, two unlabelled figures (GC-LIVE3 D5).

Recorded by the orchestrator from the verifier's returned block.
