---
work_item: W-124
ac: AC-4
requirement: REQ-087
ac_fp: "a6fbace01e0e"
result: pass
verified_by: "independent Tier A verifier (Opus, fresh context, rounds 1-2)"
builder: "builder (Sonnet, lane A cluster A3)"
date: '2026-10-22'
commands: "verifier probe cell_values; mutation put breakeven; verified sha 627acfb7d1486f5d3a5878f946b4641c7d1dd62f (round 2; round 1 on 1e5fa22d)"
---

AC: AC-4
result: pass
commands: verifier probe cell_values; mutation put breakeven; verified sha 627acfb7d1486f5d3a5878f946b4641c7d1dd62f (round 2; round 1 on 1e5fa22d)
observed: 22900 CE LTP 150.00 spot 22976.85: intrinsic 76.85, time value 73.15, breakeven 23050.00 (+0.32%); 23000 PE LTP 100: 23.15 / 76.85 / 22900.00 / -0.33%
attack: put breakeven mutation caught (2 failed)

Recorded by the orchestrator from the verifier's returned block.
