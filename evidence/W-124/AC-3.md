---
work_item: W-124
ac: AC-3
requirement: REQ-087
ac_fp: "90663acd3682"
result: pass
verified_by: "independent Tier A verifier (Opus, fresh context, rounds 1-2)"
builder: "builder (Sonnet, lane A cluster A3)"
date: '2026-10-22'
commands: "db_run pytest test_user_setting_store.py test_user_settings_allowlist_chain.py; verifier probe_db.py; verified sha 627acfb7d1486f5d3a5878f946b4641c7d1dd62f (round 2; round 1 on 1e5fa22d)"
---

AC: AC-3
result: pass
commands: db_run pytest test_user_setting_store.py test_user_settings_allowlist_chain.py; verifier probe_db.py; verified sha 627acfb7d1486f5d3a5878f946b4641c7d1dd62f (round 2; round 1 on 1e5fa22d)
observed: choices 10/20/30/40, default 10; app role grants minimal (SELECT; INSERT user_ref,key,value; UPDATE value only); downgrade refuses with a row
attack: insert of updated_at refused; downgrade guard with a row

Recorded by the orchestrator from the verifier's returned block.
