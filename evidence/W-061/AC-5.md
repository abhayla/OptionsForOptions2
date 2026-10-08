---
work_item: W-061
ac: AC-5
requirement: REQ-038
ac_fp: "c6cee64b494e"
result: pass
verified_by: "verifier (opus, fresh context)"
builder: "builder (opus)"
date: '2026-10-08'
commands: "python tools/ac_fp.py REQ-038 AC-5 --yaml; python -m pytest -q -p no:cacheprovider tests/strategy/test_stored_form.py; python -m pytest -q -p no:cacheprovider; python -m pytest -c pytest-app.ini -q -rs -p no:cacheprovider tests_app/test_strategy_store.py; gh run view 37735056280 --log; python - (offline API/domain attack scripts)"
---

AC: AC-5
result: pass
commands: python tools/ac_fp.py REQ-038 AC-5 --yaml; python -m pytest -q -p no:cacheprovider tests/strategy/test_stored_form.py; python -m pytest -q -p no:cacheprovider; python -m pytest -c pytest-app.ini -q -rs -p no:cacheprovider tests_app/test_strategy_store.py; gh run view 37735056280 --log; python - (offline API/domain attack scripts)
observed: CI (PostgreSQL, head 18ff326): migration 0007 applied, 829 passed, 3 skipped (test_entitlement_store.py:198 only), so all 23 DB tests incl. core proof ran (Save Draft 201 == expected form; dispose + new engine load equal; edit -> 1 history entry; restore -> original, history [1,2]; columns == allowlist). Local: 71 domain passed; 1783 full passed; 74 app non-DB passed, 23 DB skipped (no TEST_DATABASE_URL)
attack: 14 live-market spellings x {top level, leg, risk_limits, preferences} x {POST, PUT}: 114/114 answered 422 (map names unknown_name), no DB call; domain build and load refused all. Float strike refused, bool quantity refused, '5000.50' kept exactly. Revision conflict maps to 409, CI store test shows nothing written; another user's GET/history/restore = 404 not_found (CI). Gaps: no DB round trip with non-empty risk_limits/preferences, no API-level 409 test, no PUT-as-another-user test (code filters user_ref).

Recorded by the orchestrator from the verifier's returned block.
Recorded 2026-10-08 at PR #134 head 18ff326. Review: Tier A adversarial, 2 rounds (round 1: 1 MAJOR, 3 MINOR; round 2: 1 MAJOR, 1 MINOR - the denylist replaced by ADR-064's closed name lists), all fixed. The three coverage gaps above are filed as a deferred issue.
