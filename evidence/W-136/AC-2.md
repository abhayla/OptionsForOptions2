---
work_item: W-136
ac: AC-2
requirement: REQ-050
ac_fp: "7246ab71d200"
result: pass
verified_by: "independent verifier (Opus, fresh context, round 2 on 5a72453d)"
builder: "builder (Sonnet, builder sequence row 8: build, fix round 1, fix round 2)"
date: '2026-10-22'
commands: "round 2 (Opus) on 5a72453d: read the table/model.py diff; tests/marketdata/test_scale_classes.py; grep of cache users"
---

AC: AC-2
result: pass
commands: round 2 (Opus) on 5a72453d: read the table/model.py diff; tests/marketdata/test_scale_classes.py; grep of cache users
observed: table/model.py:460-475 checks supplied per-unit Greeks against an allow-list and never caches; rounding and position scaling stay per strategy; only 4 allow-listed files name the cache
attack: no P&L, scenario or charges code reaches the shared cache (grep)

Recorded by the orchestrator from the verifier's returned block.
