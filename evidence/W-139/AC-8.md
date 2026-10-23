---
work_item: W-139
ac: AC-8
requirement: REQ-114
ac_fp: "c144acf808f3"
result: pass
verified_by: "independent verifiers (Opus, fresh context; round 1 on b04d47f0, round 2 on 0e574b58)"
builder: "builders (Sonnet/Opus, builder sequence row 11: build, fix 1)"
date: '2026-10-23'
commands: "round 1 (Opus, fresh) on b04d47f0: test_kite_ws.py; mutants A8, A9"
---

AC: AC-8
result: pass
commands: round 1 (Opus, fresh) on b04d47f0: test_kite_ws.py; mutants A8, A9
observed: drop, reconnect and connect lines carry user=, at= and the reason; the token never appears (test_kite_ws.py:135). The 'recovered' line is not asserted by any test
attack: A8 (user removed) and A9 (URL with token logged) killed by test_kite_ws.py

Recorded by the orchestrator from the verifier's returned block.
