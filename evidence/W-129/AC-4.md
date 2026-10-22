---
work_item: W-129
ac: AC-4
requirement: REQ-001
ac_fp: "f337030b76d4"
result: pass
verified_by: "independent verifier (Sonnet, fresh context, round 2 on 3162e50f)"
builder: "builder (Sonnet, builder sequence row 1)"
date: '2026-10-22'
commands: "pytest tests/test_underlying_tables.py tests/test_underlying_one_home.py; pytest -m repo_scan tests (1005 passed); npx vitest run tests/underlyings.test.js (4 passed); scratch mutations (home + BANKNIFTY, guided.js key renamed)"
---

AC: AC-4
result: pass
commands: pytest tests/test_underlying_tables.py tests/test_underlying_one_home.py; pytest -m repo_scan tests (1005 passed); npx vitest run tests/underlyings.test.js (4 passed); scratch mutations (home + BANKNIFTY, guided.js key renamed)
observed: one home SUPPORTED_UNDERLYINGS (catalogue.py:49) with the exchange pairing; SEGMENT_BY_UNDERLYING = dict(SUPPORTED_UNDERLYINGS) (round_trip.py:24); kite_margin exchanges derived; every underlying-keyed table must hold exactly the home's keys; frontend list tied to the home by a repo test; both mutations turned tests red
attack: 25 probe shapes: the scan misses class attributes, locals, Map/let/export shapes and later .vue script blocks, and migrations 0004/0008 are not tied to the home; no real table is missed today (MINORs, deferred issue for row 46)

Recorded by the orchestrator from the verifier's returned block.
