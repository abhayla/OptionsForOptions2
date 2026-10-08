---
work_item: W-058
ac: AC-9
requirement: REQ-015
ac_fp: "fe01ad7e18db"
result: pass
verified_by: "verifier (opus, fresh context)"
builder: "builder (opus)"
date: '2026-10-08'
commands: "python -m pytest -c pytest-app.ini -q -p no:cacheprovider tests_app/test_broker_token_store.py tests_app/test_kite_login.py ; python -c <store/decrypt edge cases> ; python -c <CallbackQueryFilter encoded keys> ; gh run view 37723101139 --log"
---

AC: AC-9
result: pass
commands: python -m pytest -c pytest-app.ini -q -p no:cacheprovider tests_app/test_broker_token_store.py tests_app/test_kite_login.py ; python -c <store/decrypt edge cases> ; python -c <CallbackQueryFilter encoded keys> ; gh run view 37723101139 --log
observed: AES-GCM, fresh nonce, associated data user|broker|id; end statement nulls the ciphertext in the same UPDATE; empty token -> broker_store_invalid; SET_TOKEN miss -> broker_store_failed; REPLACED via end_session -> ValueError; short/None blob -> TokenDecryptError; encoded/mixed-case query keys redacted; CI ran the real-route core proof (ciphertext-only row, no secret in body/headers/cookies/logs), guard/grant refusals and the re-login race tests
attack: tampered/copied/other-key/empty ciphertext all treated as no session; TokenException then rollback still ends the session (CI); re-login between read and end leaves session 2 intact (CI); database evidence from CI, not run locally; live Kite login proof still pending

Recorded by the orchestrator from the verifier's returned block.
Recorded 2026-10-08 at PR #128 head ecb29b2. Review: Tier A adversarial, 2 rounds, all MAJOR findings fixed (see AC-6.md).
