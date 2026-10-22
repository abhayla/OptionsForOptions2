---
work_item: W-124
ac: AC-5
requirement: REQ-087
ac_fp: "caca48c5f62e"
result: pass
verified_by: "independent Tier A verifier (Opus, fresh context, rounds 1-2)"
builder: "builder (Sonnet, lane A cluster A3)"
date: '2026-10-22'
commands: "verifier probe.py; mutation zero-for-missing; verified sha 627acfb7d1486f5d3a5878f946b4641c7d1dd62f (round 2; round 1 on 1e5fa22d)"
---

AC: AC-5
result: pass
commands: verifier probe.py; mutation zero-for-missing; verified sha 627acfb7d1486f5d3a5878f946b4641c7d1dd62f (round 2; round 1 on 1e5fa22d)
observed: a missing or stale input gives None (dash), never 0
attack: zero-for-missing mutation caught (4 failed)

Recorded by the orchestrator from the verifier's returned block.
