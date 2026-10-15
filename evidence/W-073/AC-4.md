---
work_item: W-073
ac: AC-4
requirement: REQ-035
ac_fp: "faa18f01993e"
result: pass
verified_by: "verifier (opus, fresh context)"
builder: "builder (sonnet, worktree agent)"
date: '2026-10-15'
commands: "npx vitest run; npm run lint; npm run build; python -m pytest -q -p no:cacheprovider tests/outcome tests/errors; db_run.py <checkout> python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_outcome_socket_fallback.py tests_app/test_strategy_live_push.py tests_app/test_outcome_route.py tests_app/test_outcome_catalogue.py; npx playwright test e2e/strategy-states e2e/strategy-live e2e/leg-picker e2e/strategy-display-format (servers via dev_run.py, replay on 8001/4175); node scratchpad/attack.cjs; node scratchpad/refuse.cjs"
---

AC: AC-4
result: pass
commands: npx vitest run; npm run lint; npm run build; python -m pytest -q -p no:cacheprovider tests/outcome tests/errors; db_run.py <checkout> python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_outcome_socket_fallback.py tests_app/test_strategy_live_push.py tests_app/test_outcome_route.py tests_app/test_outcome_catalogue.py; npx playwright test e2e/strategy-states e2e/strategy-live e2e/leg-picker e2e/strategy-display-format (servers via dev_run.py, replay on 8001/4175); node scratchpad/attack.cjs; node scratchpad/refuse.cjs
observed: At 1be8edc: vitest 136 passed; lint 0; build 0; domain 731 passed; app 64 passed; Playwright 34 passed. Link lots '02'/entry '042.70' sent as 2/'42.70'; LTP cell = latest push at pushes 4,5,6,7 (30.15, 30.05, 30.15, 30.05). lots '2.0' link: state error, four parts equal to user_input_request_invalid, 0 outcome POST, 0 socket opens.
attack: Marker in the echoed push. Control (legs same) shown; lots+1, strike changed (NSE_FO:44627) and entry+0.01 never shown over 115-119 pushes each. Refusal with lots '2.0' sent no request. Gaps (not AC-4): no e2e for a non-canonical link; data-live stays live while non-matching pushes are dropped (no wrong number shown); a 20-digit lots string loses precision before the server's 10000 cap refuses it.

Recorded by the orchestrator from the verifier's returned block.
