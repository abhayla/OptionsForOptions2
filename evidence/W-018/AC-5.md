---
work_item: W-018
ac: AC-5
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/marketdata/test_disconnect.py; python -c attacks"
---

AC: AC-5
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/marketdata/test_disconnect.py; python -c attacks
observed: 7 tests incl. behaviour tests: disconnected feed -> quotes UNAVAILABLE -> strategy PAUSED -> rule CANNOT_EVALUATE; message text matches the spec byte for byte
attack: a stale but connected quote shows no disconnect message (single cause); NIFTY active / SENSEX paused split confirmed

Recorded by the orchestrator from the verifier's returned block.
