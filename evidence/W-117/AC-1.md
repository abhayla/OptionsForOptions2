---
work_item: W-117
ac: AC-1
requirement: REQ-011
ac_fp: "7aecb23a8cd1"
result: fail
verified_by: "verifier (sonnet, fresh context, Tier B, fd19b42, 2026-10-19)"
builder: "builder (W-117, sonnet)"
date: '2026-10-19'
commands: "python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_strategy_templates_route.py tests_app/test_response_door.py; python -m pytest -q -p no:cacheprovider tests/errors; cd frontend && npx vitest run tests/learn.test.js; npm run lint; python scripts/generate_openapi.py --out <scratch> then compare with docs/api/openapi.json; inline python attack script on render_explanation"
---

AC: AC-1
result: fail
commands: python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_strategy_templates_route.py tests_app/test_response_door.py; python -m pytest -q -p no:cacheprovider tests/errors; cd frontend && npx vitest run tests/learn.test.js; npm run lint; python scripts/generate_openapi.py --out <scratch> then compare with docs/api/openapi.json; inline python attack script on render_explanation
observed: AC NOT MET IN FULL (recorded as fail on purpose; the built part passed review). 215 passed; 683 passed; vitest 10 passed; lint clean; openapi equal; 21 templates equal to the loader; 42 allowed texts. PART claimed: strategy education from the reviewed catalogue holds. Options concepts and platform guidance have no content yet, only the line 'Nothing published here yet.' - REQ-011 AC-1 is not met in full.
attack: Forged, empty, 1M-char, lookalike, trailing-space, case, NFD, str-subclass, None, bytes and int inputs were all refused with TypeError. A description in the name template and another template's description were accepted (MINOR, still catalogue text; deferred). Not-live and socket-drop cases show no index number.

Recorded by the orchestrator from the verifier's returned block.
