---
work_item: W-116
ac: AC-8
requirement: REQ-029
ac_fp: "497ccbc6827a"
result: fail
verified_by: "verifier (opus, fresh context, Tier A; round 1 ff7cf11 FAIL, round 2 6562054, 2026-10-19)"
builder: "builder (W-116, opus, 2 rounds)"
date: '2026-10-19'
commands: "scratch b1.py; read the ChainOut model"
---

AC: AC-8
result: fail
commands: scratch b1.py; read the ChainOut model
observed: atm_strike follows the live spot (25398 -> 25400.00); spot served. BACKEND PART PROVEN: ATM strike and underlying price. NOT MET AS WRITTEN: highlighting, expiry selector and selected-contract highlight are screen-only (W-118); the expiry list comes from /api/catalogue/{u}/expiries, not this route.
attack: Spot on the 25175 tie and the 25225 window edge: correct ATM, 2 re-centres in 60 s.

Recorded by the orchestrator from the verifier's returned block.
