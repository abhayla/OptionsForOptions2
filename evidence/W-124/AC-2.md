---
work_item: W-124
ac: AC-2
requirement: REQ-087
ac_fp: "149c5fff9b1f"
result: pass
verified_by: "independent Tier A verifier (Opus, fresh context, rounds 1-2)"
builder: "builder (Sonnet, lane A cluster A3)"
date: '2026-10-22'
commands: "verifier probe.py; mutation fresh_spot=live_spot; verified sha 627acfb7d1486f5d3a5878f946b4641c7d1dd62f (round 2; round 1 on 1e5fa22d)"
---

AC: AC-2
result: pass
commands: verifier probe.py; mutation fresh_spot=live_spot; verified sha 627acfb7d1486f5d3a5878f946b4641c7d1dd62f (round 2; round 1 on 1e5fa22d)
observed: STALE/DELAYED spot: 0 of 10 cells carry in_the_money/intrinsic/time value/breakeven %/Greeks; atm None; spot_label 'stale since 09:20 IST'; the screen shades only when spot_health is available; mutation -> 2 failed
attack: round 1 REVISE: a stale 25162.30 shaded 25050 CE; fixed. Minor: Greeks not in the test's SPOT_KEYS (blocked in code)

Recorded by the orchestrator from the verifier's returned block.
