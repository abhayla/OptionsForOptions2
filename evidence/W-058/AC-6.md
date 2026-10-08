---
work_item: W-058
ac: AC-6
requirement: REQ-015
ac_fp: "c0c674b1a003"
result: pass
verified_by: "verifier (opus, fresh context)"
builder: "builder (opus)"
date: '2026-10-08'
commands: "python -m pytest -c pytest-app.ini -q -p no:cacheprovider tests_app/test_kite_login.py tests_app/test_broker_token_store.py -rs ; python -c <create_app().openapi() credential-word scan>"
---

AC: AC-6
result: pass
commands: python -m pytest -c pytest-app.ini -q -p no:cacheprovider tests_app/test_kite_login.py tests_app/test_broker_token_store.py -rs ; python -c <create_app().openapi() credential-word scan>
observed: 72 passed, 20 skipped (database tests); OpenAPI paths /broker/zerodha/login, /health, /kite/callback, all GET, no requestBody; callback params {status, request_token, state}; password/pin/otp/totp/twofa/2fa absent everywhere
attack: scanned the full OpenAPI JSON for credential words (none); a callback with password/pin/otp is refused broker_state_invalid, nothing echoed, no exchange; login URL is Zerodha's own page with no secret

Recorded by the orchestrator from the verifier's returned block.
Recorded 2026-10-08 at PR #128 head ecb29b2. Review: Tier A adversarial, 2 rounds (round 1: 4 MAJOR, 3 MINOR incl. CI red; round 2: 1 MAJOR, 3 MINOR), all fixed except the anonymous-lockout MINOR deferred to issue 129; builder mutation runs 6/6, 6/6 and 1/1 killed. The live owner-login core proof is still pending.
