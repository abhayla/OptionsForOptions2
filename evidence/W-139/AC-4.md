---
work_item: W-139
ac: AC-4
requirement: REQ-114
ac_fp: "a95a2078c00d"
result: pass
verified_by: "independent verifiers (Opus, fresh context; round 1 on b04d47f0, round 2 on 0e574b58)"
builder: "builders (Sonnet/Opus, builder sequence row 11: build, fix 1)"
date: '2026-10-23'
commands: "round 1 (Opus, fresh) on b04d47f0: test_kite_ws_resubscribe.py; mutant A4"
---

AC: AC-4
result: pass
commands: round 1 (Opus, fresh) on b04d47f0: test_kite_ws_resubscribe.py; mutant A4
observed: subscriptions are re-sent before on_connected (kite_ws.py run); quotes stay STALE after reconnect until a fresh tick (silence.py:79-80)
attack: A4 (on_connected moved before the subscribe) killed

Recorded by the orchestrator from the verifier's returned block.
