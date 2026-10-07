---
work_item: W-057
ac: AC-3
requirement: REQ-054
ac_fp: "971959df0111"
result: pass
verified_by: "verifier (opus, fresh context)"
builder: "builder (opus)"
date: '2026-10-07'
commands: "gh run view 37646508966 -R abhayla/OptionsForOptions2 --log | grep (pytest|SKIP|passed); python -m pytest -q -p no:cacheprovider tests_app/test_contract_identity_lifecycle.py; python -m pytest -q -p no:cacheprovider tests/instruments; python -m pytest -q -p no:cacheprovider; python -c <is_revision / Catalogue.update attacks>; python tools/ac_fp.py REQ-054 AC-3 --yaml --root <verify>"
---

AC: AC-3
result: pass
commands: gh run view 37646508966 -R abhayla/OptionsForOptions2 --log | grep (pytest|SKIP|passed); python -m pytest -q -p no:cacheprovider tests_app/test_contract_identity_lifecycle.py; python -m pytest -q -p no:cacheprovider tests/instruments; python -m pytest -q -p no:cacheprovider; python -c <is_revision / Catalogue.update attacks>; python tools/ac_fp.py REQ-054 AC-3 --yaml --root <verify>
observed: CI head 151a52a api job success: 'python -m pytest -c pytest-app.ini -q -rs' with TEST_DATABASE_URL -> '573 passed, 3 skipped', only skip test_entitlement_store.py:198 (so all 46 lifecycle tests passed in CI). Local run without the app ini or PostgreSQL: 44 failed / 2 passed (env: no pytest-asyncio, no DB). tests/instruments 53 passed; full kit suite 1641 passed.
attack: (a) same token, NIFTY CE, strike 23000->20550 and expiry moved in one list: is_revision False, update replaced=(token 1,), added=1 (new contract); the old contract is kept as delisted per the CI-passed DB test at line 432. (b) +/-6 days revision True, +/-7 days False. (c) 2 missing + 1 reuse of 21 live refused 14.3%; 1 missing + 2 reuses of 20 refused 15.0%; exactly 2 of 20 (10%) accepted. (d) expiry < IST load date skipped (skipped_expired=1, get() None), including a UTC-evening as_of that rolls into the next IST day. (e) the CI-passed DB tests assert load_contract(old_id) resolves to the old 67245/61746 contract after reuse; the live unique index predicate is NOT retired AND NOT delisted. No failure found. Minor: test docstring line 211 says '<= 7 days' (stale wording; the parameters check 6 vs 7 correctly) - corrected by the orchestrator after verification (docstring only).

Recorded by the orchestrator from the verifier's returned block.
Recorded 2026-10-07. Review: Tier A adversarial, 2 rounds (round 1: 1 CRITICAL, 2 MAJOR, 6 MINOR; round 2: 3 MAJOR, 3 MINOR incl. CI red), all fixed; builder mutation run 35/35 killed.
