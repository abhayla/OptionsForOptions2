---
work_item: W-206
requirement: REQ-159
ac: AC-6
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 4)"
date: 2026-11-04
ac_fp: "41d897082078"
commands: "env -u TEST_DATABASE_URL -u TEST_ADMIN_DATABASE_URL -u ALEMBIC_DATABASE_URL python -m pytest -q -p no:cacheprovider tests/adjustment/test_liquidity.py tests/adjustment/test_guard_debit_paise.py; env -u TEST_DATABASE_URL -u TEST_ADMIN_DATABASE_URL -u ALEMBIC_DATABASE_URL python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_t19_limits.py; grep hide_oi_below|roll_debit_limit|max_adjustments|warn_cost backend frontend/src; read backend/ofo/adjustment/guard_readers.json; read backend/ofo_app/adjustment_check.py:203-229, routes/adjustment.py:166-172"
---
48 + 6 passed. Wired: liquidity_inputs (routes/adjustment.py:171) feeds the compare (:489) and the worker's cheapest_offered (adjustment_check.py:221); guard_debit runs on every roll (approaches.py:418-462); max_adjustments read at playbook_eval.py:502 and offered.py:27; buy-first ordering at approaches.py:555. FAIL: the cost warning warn_cost_pct_of_premium_left (default '50') has no reader - guard_readers.json:16 says 'no reader today' and grep finds none; the compare shows a cost % but never warns against the saved threshold.

REQ-159.md:91-94 is stale: F-77/F-78 described as unbuilt although liquidity and roll-debit are applied (ADR-230).

Recorded by the orchestrator from the verifier's returned block.
