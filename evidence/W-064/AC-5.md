---
work_item: W-064
ac: AC-5
requirement: REQ-035
ac_fp: "0159ea3c8e7b"
result: pass
verified_by: "verifier (sonnet, fresh context, final state 14b5a98)"
builder: "builder (sonnet, 3 rounds)"
date: '2026-10-09'
commands: "python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_outcome_route.py tests_app/test_replay_mode.py; python -m pytest -q -p no:cacheprovider tests/outcome; python -m pytest -q -p no:cacheprovider; raw HTTP POST /api/strategies/outcome at ux none/guided/standard/advanced; independent read_snapshot comparison; playwright strategy-table.spec.ts"
---

AC: AC-5
result: pass
commands: python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_outcome_route.py tests_app/test_replay_mode.py; python -m pytest -q -p no:cacheprovider tests/outcome; python -m pytest -q -p no:cacheprovider; raw HTTP POST /api/strategies/outcome at ux none/guided/standard/advanced; independent read_snapshot comparison; playwright strategy-table.spec.ts
observed: app 17 passed, outcome domain 15 passed, full domain 2588 passed; raw JSON: the advanced_details key and the strings bid/ask absent at none/guided/standard, present at advanced for 4 legs with bid/ask equal to an independent snapshot read (39/39.1, 12.9/12.95, 82.45/82.65, 35.85/35.95); e2e AC-5 passed at 390 and 1280
attack: Unknown instrument at advanced: REFUSED state with null bid/ask, no crash. A Standard page given an injected advanced_details block rendered no Advanced section. An Advanced page with a tampered bid 123.456 showed it exactly as sent (no browser maths). Bid/ask are not table columns at any level (REQ-035 AC-2 order kept).

Recorded by the orchestrator from the verifier's returned block.
