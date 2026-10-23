---
work_item: W-139
ac: AC-3
requirement: REQ-114
ac_fp: "1a4c156de05a"
result: pass
verified_by: "independent verifiers (Opus, fresh context; round 1 on b04d47f0, round 2 on 0e574b58)"
builder: "builders (Sonnet/Opus, builder sequence row 11: build, fix 1)"
date: '2026-10-23'
commands: "round 1 (Opus, fresh) on b04d47f0: tests/marketdata/test_reconnect_policy.py; mutants K1-K3, A3"
---

AC: AC-3
result: pass
commands: round 1 (Opus, fresh) on b04d47f0: tests/marketdata/test_reconnect_policy.py; mutants K1-K3, A3
observed: waits 1, 2, 4 s doubling, capped at 30 s, jitter takes 0-50% off each wait (reconnect_policy.py:30-37); a drop before the first data frame does not reset the back-off (silence.py:117)
attack: K1 (no jitter), K2 (jitter above the cap), K3 (no cap) and A3 (reset on connect, the storm case) all killed

Recorded by the orchestrator from the verifier's returned block.
