---
work_item: W-150
ac: AC-3
requirement: REQ-034
ac_fp: "d9f15e7fba6e"
result: pass
verified_by: "independent verifiers (Opus row 22 check + round 2 on f5ab7f1e; Sonnet AC-1/5/7 re-check on bf4823e7; Sonnet 22b check on e928a3af)"
builder: "builders (Opus: row 22 d0a6049f, ATM-IV fix f5ab7f1e; Sonnet: 22b e928a3af)"
date: '2026-10-24'
commands: "same suite; tests/scenario/test_levels.py"
---

AC: AC-3
result: pass
commands: same suite; tests/scenario/test_levels.py
observed: default NIFTY range 21500..23500 unchanged by a 330-point move; step 100
attack: narrow config (100 step) widens to 22000..23100, still on 100-point steps

Recorded by the orchestrator from the verifier's returned block.
