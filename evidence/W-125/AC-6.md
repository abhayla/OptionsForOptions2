---
work_item: W-125
ac: AC-6
requirement: REQ-079
ac_fp: "7fe2dc476a74"
result: pass
verified_by: "independent Tier A verifier (Opus, fresh context)"
builder: "builder (Sonnet, lane B cluster B4)"
date: '2026-10-22'
commands: "db_run pytest tests_app/test_ready_made_route.py; verifier attack.py; verified sha 0f1704039dbe4f6e471c64e20776ef96e85f8404"
---

AC: AC-6
result: pass
commands: db_run pytest tests_app/test_ready_made_route.py; verifier attack.py; verified sha 0f1704039dbe4f6e471c64e20776ef96e85f8404
observed: missing expiry -> EXPIRY_MISSING refusal, a catalogue message, no server error
attack: all expiry slots set to None

Recorded by the orchestrator from the verifier's returned block.
