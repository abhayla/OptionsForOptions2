---
work_item: W-214
requirement: REQ-170
ac: AC-4
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 3)"
date: 2026-11-03
ac_fp: "5b0d7d9e0a7d"
commands: "cd frontend && npx vitest run tests/adjustment-opportunities.test.js; env -u TEST_DATABASE_URL -u TEST_ADMIN_DATABASE_URL -u ALEMBIC_DATABASE_URL python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_adjustment_held_timeline.py; read held_reasons.py, adjustment_opportunities.py, AdjustmentOpportunitiesPage.vue, playbook_store._HELD_INBOX, background.py:590, explanations.py:1915"
---
vitest 20 passed incl. the held test (both reasons render with the server text and IST time; no Compare or Dismiss on held rows); DB tests 3 skipped. The worker stores each Held event via record_held (background.py:592); GET /api/adjustment-opportunities returns `held` from adjustment_held_crossings, user-scoped, with 'held: daily limit' / 'held: quiet time' from the catalogue; HeldOut carries no can_act or outcome and is not counted.

Met as the held list on the Adjustment opportunities page with the strategy named per row, not in the builder's per-strategy view. DB proof owed: tests_app/test_adjustment_held_timeline.py (3 tests).

Recorded by the orchestrator from the verifier's returned block.
