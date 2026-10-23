---
work_item: W-130
ac: AC-7
requirement: REQ-015
ac_fp: "2898ddc60724"
result: pass
verified_by: "independent verifier (Opus, fresh context, round 2 on 8a23776f)"
builder: "builder (Sonnet, builder sequence row 2)"
date: '2026-10-22'
commands: "start verifier: grep DELETE FROM|TRUNCATE backend/ofo_app; db_run pytest tests_app/test_broker_token_store.py; rounds 1-2: git diff --stat"
---

AC: AC-7
result: pass
commands: start verifier: grep DELETE FROM|TRUNCATE backend/ofo_app; db_run pytest tests_app/test_broker_token_store.py; rounds 1-2: git diff --stat
observed: expiry ends the session row only (UPDATE broker_sessions SET ended_at, end_reason, token_ciphertext=NULL; broker_token_store.py:35-39,105); no DELETE in app code, no DELETE grant (0007:21); history job with no stored session exits 4, deletes nothing
attack: any expiry path writing outside broker_sessions: none

Recorded by the orchestrator from the verifier's returned block.
