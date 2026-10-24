---
work_item: W-152
ac: AC-3
requirement: REQ-133
ac_fp: "a2ee03774c7a"
result: pass
verified_by: "independent verifier (Opus row 24 check on 7e9f5ee4, reproduced step 1 on the base)"
builder: "builders (Opus: row 24 20cdbbc1; Sonnet finisher 7e9f5ee4; orchestrator pin for outcome_waiting_first_price)"
date: '2026-10-24'
commands: "checker probe.py on the base backend (8f317c6f) vs HEAD on the recorded 2026-10-08 replay; pytest -c pytest-app.ini -k req133 on base and HEAD; orchestrator mutation gate: wait never on, wait past the limit - killed"
---

AC: AC-3
result: pass
commands: checker probe.py on the base backend (8f317c6f) vs HEAD on the recorded 2026-10-08 replay; pytest -c pytest-app.ini -k req133 on base and HEAD; orchestrator mutation gate: wait never on, wait past the limit - killed
observed: Base: a server Kite-feed reconnect before its first tick answered COMPUTED 'Live market data disconnected...' with every leg 'stale since 09:20 IST' (F-61); HEAD: NOT_CONNECTED 'Waiting for the first live price', no LTP, no table; past FEED_STALE + 1 ms with no price the stale alarm returns; a browser-socket reconnect was already correct on the base
attack: heartbeat during the wait (still waiting, then the alarm); reconnect then 60 s silence (alarm); silence after a price never waits (feed_health.py:144); ended session and fallback give FROM_ENTRIES; Execute needs COMPUTED, so it stays disabled while waiting. MINORs (#532): the Builder's not-connected sentence and the card's paused badge show during the up-to-3 s wait

Recorded by the orchestrator from the verifier's returned block.
