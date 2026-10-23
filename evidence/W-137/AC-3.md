---
work_item: W-137
ac: AC-3
requirement: REQ-113
ac_fp: "f60bce758463"
result: pass
verified_by: "independent verifiers (Opus, fresh context; final round on 4b829faf)"
builder: "builders (Sonnet, builder sequence row 9: parts A0, A1, B, C and their fix/finish rounds)"
date: '2026-10-23'
commands: "final round: DB run; mutant M10; A0 r2 and A1+C rounds (mutation sweeps)"
---

AC: AC-3
result: pass
commands: final round: DB run; mutant M10; A0 r2 and A1+C rounds (mutation sweeps)
observed: Redis Streams bus (F-58) only once two processes run; feed mode is an allow-list, inprocess refused in production with LIVE_MARKET; rebuildable state only (expiring keys, capped streams); a Redis loss marks prices stale until a frame the feed received after the loss (BusSocket._lost, feed_bus.py); the feed recovers when Redis is down at start (feed_main.py:173-179)
attack: Redis refused at feed start -> killed; frame received before the loss shown live -> killed; API stamping its own clock (M04) -> killed (A0 r2)

Recorded by the orchestrator from the verifier's returned block.
