---
work_item: W-138
ac: AC-5
requirement: REQ-118
ac_fp: "f8c77be6a711"
result: pass
verified_by: "independent verifiers (Opus, fresh context; round 2 on 962ab74c)"
builder: "builders (Sonnet, builder sequence row 10: build, finish, finish 2, fix 1)"
date: '2026-10-23'
commands: "round 2 DB run; round 1 mutants v4-v7; finish 1 M8/M9/M9b through every sender"
---

AC: AC-5
result: pass
commands: round 2 DB run; round 1 mutants v4-v7; finish 1 M8/M9/M9b through every sender
observed: the one write that exists, POST /session/token, is never retried on a 429 or timeout (kite_http.py:209, ofo_app/kite_http.py:271); trigger writes are not built - that part is deferred to the order path (REQ-100)
attack: 429 and timeout on the login exchange reach the fake server exactly once through urllib, sync and async httpx

Recorded by the orchestrator from the verifier's returned block.
