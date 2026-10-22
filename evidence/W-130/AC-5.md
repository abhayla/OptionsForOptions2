---
work_item: W-130
ac: AC-5
requirement: REQ-015
ac_fp: "02f085000f3d"
result: pass
verified_by: "independent verifier (Opus, fresh context, round 2 on 8a23776f)"
builder: "builder (Sonnet, builder sequence row 2)"
date: '2026-10-22'
commands: "rounds 1-2: read kite_ws.py _start_reconnect_read, live_market._read_positions_once, kite_reads._fetch; pytest tests_app/test_reconnect_positions_read.py (15 passed)"
---

AC: AC-5
result: pass
commands: rounds 1-2: read kite_ws.py _start_reconnect_read, live_market._read_positions_once, kite_reads._fetch; pytest tests_app/test_reconnect_positions_read.py (15 passed)
observed: automatic reconnect with backoff and re-subscribe; on a RE-connect only (connections >= 2) one positions read via KiteReads.fetch_positions, as its own task, never two at once, no retry, errors logged by code; a 403 ends the session (no renewal). The reconcile part of 'validates and resynchronises' (Trigger.AFTER_RECONNECT) is deferred to the order path (REQ-060, ADR-165)
attack: traced every call reachable from on_reconnect: no order call; a flapping socket gives at most one read per reopen. Live drop not done today (live check pending for row 63: cut the network in market hours, see a reconnect log line, new frames and one positions read)

Recorded by the orchestrator from the verifier's returned block.
