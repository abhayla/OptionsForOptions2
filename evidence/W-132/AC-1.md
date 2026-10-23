---
work_item: W-132
ac: AC-1
requirement: REQ-117
ac_fp: "cbfb54d0e8f0"
result: pass
verified_by: "independent verifier (Opus, fresh context, round 2 on 23eee95b)"
builder: "builder (Sonnet, builder sequence row 4: build, finish, fix round 1)"
date: '2026-10-22'
commands: "round 2 (Opus) on 23eee95b: pytest tests/broker + execution + scan (277 passed); db_run pytest tests_app/test_broker_capabilities_route.py test_kite_broker_reader.py (0 skipped); round 1 flag_attacks.py"
---

AC: AC-1
result: pass
commands: round 2 (Opus) on 23eee95b: pytest tests/broker + execution + scan (277 passed); db_run pytest tests_app/test_broker_capabilities_route.py test_kite_broker_reader.py (0 skipped); round 1 flag_attacks.py
observed: BrokerFlag holds exactly the 7 flags (backend/ofo/broker/flags.py:31-40); KiteBrokerReader.capabilities and the BrokerReader protocol carry them; GET /api/broker/capabilities answers the 7 as booleans, no source text, no broker name
attack: unknown, None, int, empty names -> off; an unknown or misspelled name in the file refuses the whole load; the FlagSet cannot change after load

Recorded by the orchestrator from the verifier's returned block.
