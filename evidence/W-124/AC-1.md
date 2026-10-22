---
work_item: W-124
ac: AC-1
requirement: REQ-087
ac_fp: "b5a5369f0049"
result: pass
verified_by: "independent Tier A verifier (Opus, fresh context, rounds 1-2)"
builder: "builder (Sonnet, lane A cluster A3)"
date: '2026-10-22'
commands: "verifier probe.py; pytest tests_app/test_chain_stale_spot.py tests_app/test_chain_live.py tests/test_chain_values.py; verified sha 627acfb7d1486f5d3a5878f946b4641c7d1dd62f (round 2; round 1 on 1e5fa22d)"
---

AC: AC-1
result: pass
commands: verifier probe.py; pytest tests_app/test_chain_stale_spot.py tests_app/test_chain_live.py tests/test_chain_values.py; verified sha 627acfb7d1486f5d3a5878f946b4641c7d1dd62f (round 2; round 1 on 1e5fa22d)
observed: per lot 702.65 x 65 = 45672.25 (round 1); CE25050 lot 75, ltp 131.00, per_lot 9825.00 under every spot health; 75 passed
attack: LTP 0 and missing LTP give per_lot None

Recorded by the orchestrator from the verifier's returned block.
