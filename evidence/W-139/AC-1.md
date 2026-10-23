---
work_item: W-139
ac: AC-1
requirement: REQ-114
ac_fp: "8927d10bd91d"
result: pass
verified_by: "independent verifiers (Opus, fresh context; round 1 on b04d47f0, round 2 on 0e574b58)"
builder: "builders (Sonnet/Opus, builder sequence row 11: build, fix 1)"
date: '2026-10-23'
commands: "round 1 (Opus, fresh) on b04d47f0: pytest -c pytest-app.ini test_kite_ws_silence.py test_kite_ws_resubscribe.py test_kite_ws.py (22 passed); mutants A1, A6"
---

AC: AC-1
result: pass
commands: round 1 (Opus, fresh) on b04d47f0: pytest -c pytest-app.ini test_kite_ws_silence.py test_kite_ws_resubscribe.py test_kite_ws.py (22 passed); mutants A1, A6
observed: silence is measured on the connection's last frame, heartbeats included (kite_ws.py _pump/_health_check); a check runs at least every 15 s (test_kite_ws_silence.py:106); 10 minutes of heartbeats with no ticks gives 0 reconnects (:83)
attack: A1 (heartbeat stops counting as a frame) killed; A6 (no check on a quiet poll) killed

Recorded by the orchestrator from the verifier's returned block.
