---
work_item: W-130
ac: AC-8
requirement: REQ-015
ac_fp: "977156f2d8a7"
result: pass
verified_by: "independent verifier (Opus, fresh context, round 2 on 8a23776f)"
builder: "builder (Sonnet, builder sequence row 2)"
date: '2026-10-22'
commands: "start verifier: read broker_status.py:112-121; db_run pytest tests_app/test_broker_disconnect.py; rounds 1-2: diff check (Disconnect never pressed)"
---

AC: AC-8
result: pass
commands: start verifier: read broker_status.py:112-121; db_run pytest tests_app/test_broker_disconnect.py; rounds 1-2: diff check (Disconnect never pressed)
observed: Disconnect ends the session, stops the live socket and forgets the sync time; every other table unchanged (test passes); execution/positions refuse with the connect prompt until reconnect
attack: GET cannot disconnect; anonymous caller cannot end the session; no change in the row-2 diff

Recorded by the orchestrator from the verifier's returned block.
