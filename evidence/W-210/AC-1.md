---
work_item: W-210
requirement: REQ-163
ac: AC-1
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 3)"
date: 2026-11-03
ac_fp: "000fc036a329"
commands: "env -u TEST_DATABASE_URL -u TEST_ADMIN_DATABASE_URL -u ALEMBIC_DATABASE_URL python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_adjustment_history_why.py; cd frontend && npx vitest run tests/adjust-acted-handoff.test.js; read playbook_store.py:273-290,654-685; routes/paper.py:722-745; routes/adjustment_history.py:150-300; StrategyBuilderPage.vue; tracking.js"
---
Non-DB: 1 passed, 1 skipped (_why answer states); vitest handoff 6 passed. paper.py:728-729 links each id inside the placement transaction (a StrategyStoreError rolls back); _LINK_ORDERS requires same strategy, same user, outcome acted_on and no earlier orders_placed entry, else NOT_FOUND / NOT_OPEN; placed_links maps each order to every record; _why gives the condition line for one, a count line plus lines for several, 'Your own change' for none. Attack: a basket at another time has no link -> 'Your own change'; another strategy's record is refused by the SQL.

DB proof owed: tests_app/test_adjustment_history_why.py::test_an_adjustment_from_a_suggestion_names_its_rule_and_every_bad_link_is_refused (read, not run).

Recorded by the orchestrator from the verifier's returned block.
