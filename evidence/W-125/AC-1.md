---
work_item: W-125
ac: AC-1
requirement: REQ-079
ac_fp: "8fd6858195c5"
result: pass
verified_by: "independent Tier A verifier (Opus, fresh context)"
builder: "builder (Sonnet, lane B cluster B4)"
date: '2026-10-22'
commands: "db_run pytest tests_app/test_held_switches.py; verifier attack.py; verified sha 0f1704039dbe4f6e471c64e20776ef96e85f8404"
---

AC: AC-1
result: pass
commands: db_run pytest tests_app/test_held_switches.py; verifier attack.py; verified sha 0f1704039dbe4f6e471c64e20776ef96e85f8404
observed: off in production/staging/unset and spelling variants; on only in development/test; screens use v-if on the exact listed name
attack: APP_ENV 'Development',' test','dev','staging'; ignore-reference mutation turned 4 tests red

Recorded by the orchestrator from the verifier's returned block.
