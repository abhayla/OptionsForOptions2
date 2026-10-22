---
work_item: W-127
ac: AC-6
requirement: REQ-084
ac_fp: "da62a2ab6588"
result: pass
verified_by: "independent Tier A verifier (Opus, fresh context)"
builder: "builder (Sonnet, lane B cluster B2)"
date: '2026-10-22'
commands: "db_run pytest tests_app/test_whatif_route.py; verified sha 25e33c3af33b62622d2fa5ac060d1513ee8bee65"
---

AC: AC-6
result: pass
commands: db_run pytest tests_app/test_whatif_route.py; verified sha 25e33c3af33b62622d2fa5ac060d1513ee8bee65
observed: 6 passed; what-if inputs absent from the stored definition
attack: same request with and without inputs -> same expiry curve

Recorded by the orchestrator from the verifier's returned block.
