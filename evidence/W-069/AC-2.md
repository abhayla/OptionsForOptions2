---
work_item: W-069
ac: AC-2
requirement: REQ-065
ac_fp: "d1023ce348f1"
result: pass
verified_by: "verifier (sonnet, fresh context, 2026-10-11, at 28a8f0d)"
builder: "builder (sonnet; round 1 + fix rounds pricing-scan and Tier A, 2026-10-11)"
date: '2026-10-11'
commands: "python tools/ac_fp.py REQ-065 AC-2 --yaml (orchestrator); python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_response_door.py tests_app/test_api_models.py tests_app/test_apimodel_closed.py tests_app/test_error_boundary.py ; python -m pytest -q -p no:cacheprovider (log: scratchpad/v-root.log) ; ad-hoc python heredoc attack scripts over create_app() with TestClient under APP_ENV=production and development ; two in-process mutation runs of pytest (Boundary bypassed; _model_tree replaced by model_dump)"
---

AC: AC-2
result: pass
commands: python tools/ac_fp.py REQ-065 AC-2 --yaml (orchestrator); python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_response_door.py tests_app/test_api_models.py tests_app/test_apimodel_closed.py tests_app/test_error_boundary.py ; python -m pytest -q -p no:cacheprovider (log: scratchpad/v-root.log) ; ad-hoc python heredoc attack scripts over create_app() with TestClient under APP_ENV=production and development ; two in-process mutation runs of pytest (Boundary bypassed; _model_tree replaced by model_dump)
observed: 4 required files: 107 passed. Root suite: 2915 passed in 92.30s. Real refusal route GET /api/broker/refusals/broker_state_invalid returns 200 with the catalogue body (golden bytes asserted by test_core_the_real_refusal_route_answers_todays_bytes). Attacks all gave the catalogue four-part body, no sentence: route returning a dict, JSONResponse, Response, PlainTextResponse, a plain BaseModel, a response_model subclass, a mounted raw ASGI app -> 500 INTERNAL_SYSTEM_002 with a reference id; HTTPException(418/400/500, sentence) -> USER_INPUT_003 at its own status (500 -> internal); dependency raising HTTPException or ValueError carrying the sentence -> clean; 404 /nope, 405 POST /health, 422 int-parse error -> USER_INPUT_003/002; APP_ENV=production /docs, /redoc, /openapi.json -> 404 USER_INPUT_003; APP_ENV=development /docs and /openapi.json -> 200 (exempt by design, ADR-073). Error responses carry cache-control no-store and referrer-policy no-referrer. GET /health gave a clean 500 because DATABASE_URL is unset here, so no DB was touched.
attack: Mutation 1: replacing _Boundary.__call__ with a pass-through made test_an_unsealed_response_from_anywhere_else_is_dropped_whole_and_answered_500 fail with the sentence in the 200 body, so the seal tests are not vacuous. Mutation 2: replacing _model_tree with model_dump made 6+ tests in test_response_door.py fail (extras, swapped value, field-name pattern, money format, subclass/tuple), so the walk is covered. Residual: exception-supplied Allow / WWW-Authenticate header VALUES pass through unchanged (sentence reached the header; body clean). Same class as the known header-values follow-up (#197); not an AC-2 body failure. Also confirmed that POST /api/strategies/outcome is exempt from the seal by exact method and path until W-066.

Recorded by the orchestrator from the verifier's returned block.
