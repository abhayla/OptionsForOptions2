---
work_item: W-130
ac: AC-4
requirement: REQ-015
ac_fp: "a36576dc48a4"
result: pass
verified_by: "independent verifier (Opus, fresh context, round 2 on 8a23776f)"
builder: "builder (Sonnet, builder sequence row 2)"
date: '2026-10-22'
commands: "round 2 on 8a23776f: db_run pytest tests_app/test_live_feed_status.py test_connect_gate_routes.py test_broker_status_route.py test_reconnect_positions_read.py; vitest broker-settings positions-page (21 passed); live probe.py; phase_attack.py. Orchestrator after round 2: test_broker_status_route.py expectation updated (one assertion: KiteProvider([]) with nothing subscribed expects live_feed_idle, the new correct state), db_run pytest on the 4 files -> 49 passed, 0 skipped; live readings 11:59-12:00 IST on 8a23776f"
---

AC: AC-4
result: pass
commands: round 2 on 8a23776f: db_run pytest tests_app/test_live_feed_status.py test_connect_gate_routes.py test_broker_status_route.py test_reconnect_positions_read.py; vitest broker-settings positions-page (21 passed); live probe.py; phase_attack.py. Orchestrator after round 2: test_broker_status_route.py expectation updated (one assertion: KiteProvider([]) with nothing subscribed expects live_feed_idle, the new correct state), db_run pytest on the 4 files -> 49 passed, 0 skipped; live readings 11:59-12:00 IST on 8a23776f
observed: live row from the feed's PRICE-frame time (feed_health.py:83-92): connected only with a price frame within feed_stale; subscribed and no frame -> live_feed_waiting; nothing subscribed -> live_feed_idle; backoff -> live_feed_reconnecting; 403 -> live_feed_session_ended; live: no screen -> idle, screen open (NIFTY 22631.05) -> connected, 5/15/30 s after close -> idle; four separate status rows with fix texts on the Settings page
attack: round 1: heartbeats kept the row connected forever (finding keepalive-counted-as-live-data, fixed); round 2: never-ticking subscribed contract -> waiting; reconnect needs a fresh price frame; exactly 3 s healthy, 3 s + 1 us waiting. Residual MINOR: up to ~3 s connected after the last screen closes (unwanted ticks still call on_data); after market close a quiet screen advises Reconnect (deferred issue)

Recorded by the orchestrator from the verifier's returned block.
