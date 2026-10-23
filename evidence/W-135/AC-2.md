---
work_item: W-135
ac: AC-2
requirement: REQ-049
ac_fp: "f8b26fc11ea2"
result: pass
verified_by: "independent verifier (Opus, fresh context, round 1 on c908b5b0)"
builder: "builder (Sonnet, builder sequence row 7)"
date: '2026-10-22'
commands: "verifier: tests/marketdata/test_feed_health_replay.py, test_fix_round1.py; mutate.py M1/M2 (killed); FanOut script on the recorded frames"
---

AC: AC-2
result: pass
commands: verifier: tests/marketdata/test_feed_health_replay.py, test_fix_round1.py; mutate.py M1/M2 (killed); FanOut script on the recorded frames
observed: kite_provider.py:78 counts a frame as live data only when it carries a tick for a token currently wanted (#513 item 1); a token held by two screens stays healthy when one leaves; after both leave a 552-tick frame reads waiting; a heartbeat alone waits; F-32: 982 quiet quotes stay AVAILABLE after 61 s on a healthy feed
attack: one wanted tick among many unwanted; token released between frames; shared token; index tokens; heartbeat only

Recorded by the orchestrator from the verifier's returned block.
