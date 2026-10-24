---
work_item: W-151
ac: AC-1
requirement: REQ-119
ac_fp: "0ce528c6ac07"
result: pass
verified_by: "independent verifiers (Opus 23a check, round 2, redesign check; Opus 23b check, round 2)"
builder: "builders (Opus: 23a 3d57accf/e724981b + orchestrator lint 8ca82154, Sonnet fix 220923e9, Opus independent redesign c2e921bd; Sonnet: 23b 00b8ecba, fix f7445753)"
date: '2026-10-24'
commands: "server half (23a redesign check on c2e921bd): select_app_tests.py then pytest -c pytest-app.ini on 84 DB-free files (1710 passed, 400 skipped); probe through execute_strategy with seq 5 / none. Browser half (23b round 2 on f7445753): npx vitest run tests/strategy-live.test.js tests/newest-wins.test.js tests/leg-edit.test.js tests/leg-picker.test.js tests/execute-screen.test.js tests/outcome-view.test.js (184 passed); probe zz-probe-23b-r2"
---

AC: AC-1
result: pass
commands: server half (23a redesign check on c2e921bd): select_app_tests.py then pytest -c pytest-app.ini on 84 DB-free files (1710 passed, 400 skipped); probe through execute_strategy with seq 5 / none. Browser half (23b round 2 on f7445753): npx vitest run tests/strategy-live.test.js tests/newest-wins.test.js tests/leg-edit.test.js tests/leg-picker.test.js tests/execute-screen.test.js tests/outcome-view.test.js (184 passed); probe zz-probe-23b-r2
observed: Outcome, leg-edit and Execute requests from the builder screens carry seq (outcome:1,2,3 / leg-edit:1,2 / execute:1); the server echoes it unchanged through one helper echo_seq (backend/ofo_app/api_models.py) on a real ExecuteOut; seq absent -> no key; table and margin come inside the outcome reply.
attack: two kinds in flight at once keep their own increasing seq; ApiModel.model_copy still refused; a seq+1 mutant fails 15 tests. MINOR: the reply field re-validates leniently ('5'->5), unreachable because the request field is strict.

Recorded by the orchestrator from the verifier's returned block.
