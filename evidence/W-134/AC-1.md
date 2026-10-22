---
work_item: W-134
ac: AC-1
requirement: REQ-048
ac_fp: "053ef3ee993e"
result: pass
verified_by: "independent verifier (Opus, fresh context, round 2 on 06c5c958)"
builder: "builder (Sonnet, builder sequence row 6: build, fix round 1)"
date: '2026-10-22'
commands: "rounds 1-2 (Opus): pytest tests/marketdata/test_pipeline_stages.py (recorded frames-2026-10-08-092000-10s); mutations 'fan-out drops half' and 'fan-out changes ltp' killed"
---

AC: AC-1
result: pass
commands: rounds 1-2 (Opus): pytest tests/marketdata/test_pipeline_stages.py (recorded frames-2026-10-08-092000-10s); mutations 'fan-out drops half' and 'fan-out changes ltp' killed
observed: the recorded frames reach a subscriber only through provider -> normalised quote -> latest-quote store (the in-process fast cache while one process serves; row 9 REQ-113 owns the shared cache) -> fan-out -> platform socket, one quote per recorded tick, last LTP equal to the last frame; an import-graph allow-list names which modules may import each stage
attack: a planted module importing the provider to feed a screen is red; routes read the book only through the live_market facade

Recorded by the orchestrator from the verifier's returned block.
