---
work_item: W-130
ac: AC-9
requirement: REQ-015
ac_fp: "fe01ad7e18db"
result: pass
verified_by: "independent verifier (Opus, fresh context, round 2 on 8a23776f)"
builder: "builder (Sonnet, builder sequence row 2)"
date: '2026-10-22'
commands: "rounds 1-2: grep environ/getenv TOKEN in backend and scripts; grep log calls with token"
---

AC: AC-9
result: pass
commands: rounds 1-2: grep environ/getenv TOKEN in backend and scripts; grep log calls with token
observed: token only as AES-GCM ciphertext in the session store (broker_crypto.py, broker_token_store.py); history_finalize.py now reads it through access_token_for and ignores KITE_ACCESS_TOKEN (test sets the variable to prove it); socket URL never logged; new except paths log class or code only
attack: start state found the env read in history_finalize.py:67 (fixed 3d9e5a4a); any other env token read or logged token: none

Recorded by the orchestrator from the verifier's returned block.
