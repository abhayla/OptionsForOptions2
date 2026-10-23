---
work_item: W-138
ac: AC-2
requirement: REQ-118
ac_fp: "aaaaf39a9d93"
result: pass
verified_by: "independent verifiers (Opus, fresh context; round 2 on 962ab74c)"
builder: "builders (Sonnet, builder sequence row 10: build, finish, finish 2, fix 1)"
date: '2026-10-23'
commands: "round 2: guard line (1366 passed), -m repo_scan (1216 passed), mutant r2-a2; round 1 mutants v1, v2, v3, v8"
---

AC: AC-2
result: pass
commands: round 2: guard line (1366 passed), -m repo_scan (1216 passed), mutant r2-a2; round 1 mutants v1, v2, v3, v8
observed: all three senders call the one limiter (ofo/broker/kite_http.py:201 urllib; ofo_app/kite_http.py:264 sync, :336 async); no other urllib/httpx/kiteconnect call in backend; the door-coverage scan fails closed
attack: limiter removed from each door / keyless skipping the limiter -> killed

Recorded by the orchestrator from the verifier's returned block.
