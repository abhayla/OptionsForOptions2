---
work_item: W-121
ac: AC-6
requirement: REQ-073
ac_fp: "760fadc5a794"
result: pass
verified_by: "independent Tier A verifier (Opus, fresh context)"
builder: "builder (Sonnet, agent worktree)"
date: '2026-10-21'
commands: "python scripts/orchestrator/db_run.py <worktree> python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_order_path_switch.py ; the same on scratch mutants m1 (execute guard removed), m2 (APP_ENV check removed), m3 (return guard removed) ; db_run.py on main, origin/main, branch: tests_app/test_execute_drift_block.py ; cd frontend && npx vitest run order-path-off ; scratch tests_app/test_gap.py"
---

AC: AC-6
result: pass
commands: python scripts/orchestrator/db_run.py <worktree> python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_order_path_switch.py ; the same on scratch mutants m1 (execute guard removed), m2 (APP_ENV check removed), m3 (return guard removed) ; db_run.py on main, origin/main, branch: tests_app/test_execute_drift_block.py ; cd frontend && npx vitest run order-path-off ; scratch tests_app/test_gap.py
observed: 67 passed; m1 5 failed/62 passed; m2 46 failed/21 passed; m3 5 failed/62 passed; drift-block 8 failed on main, origin/main and branch (same 'Catalogue update refused: would drop 207 of 208' error, so not a regression); vitest 27 passed; test_gap UNGUARDED: [] (MINOR-1, deferred)
attack: Three guard mutants all turn red. Unlisted flag value 'enabled' is off. No route other than execute/return imports an order module. OFO_ORDER_PATH is set only on the two order-test steps of app-tests.yml; no APP_ENV=test in any deploy, env or script file. Frontend fails closed on 10 answer states and guards both routes. MINOR-1: a route reaching basket_post through a helper module is not caught by the scan (verified sha ff7be0a594c5df375d1109f17c91c0990e49d848).

Recorded by the orchestrator from the verifier's returned block.
