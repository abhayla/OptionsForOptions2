---
work_item: W-149
ac: AC-1
requirement: REQ-077
ac_fp: "7672705058a5"
result: pass
verified_by: "independent verifiers (Opus part checks 21m/21b/21a/21d with round 2; Sonnet 21c check + round 2; Opus CI-fix check + round 2; Opus row 21 closing check on 9730cda2)"
builder: "builders (Opus: 21m 8a3bf0d2, 21b 8f5dc56e, 21a c851c84d, 21d 6d4ae53f; Sonnet: 21c f1a5e938 + fix 264576bb, CI fix 6bac88cf..ab38cd8d)"
date: '2026-10-24'
commands: "npx vitest run tests/leg-edit.test.js tests/save-draft.test.js tests/leg-picker.test.js tests/strategy-live.test.js tests/execute-screen.test.js; python -m pytest -q -p no:cacheprovider -c pytest-app.ini <72 select_app_tests files> (DATABASE_URL unset); mutant runner on leg_edit.py"
---

AC: AC-1
result: pass
commands: npx vitest run tests/leg-edit.test.js tests/save-draft.test.js tests/leg-picker.test.js tests/strategy-live.test.js tests/execute-screen.test.js; python -m pytest -q -p no:cacheprovider -c pytest-app.ini <72 select_app_tests files> (DATABASE_URL unset); mutant runner on leg_edit.py
observed: vitest 172 passed; app 1582 passed, 299 skipped. Backend: leg_edit.py:361-362 stamps a typed price with now(); :387 price_source 'typed' when x.typed else 'captured'; set_typed_price (ofo/strategy/leg_edit.py:168) stores value.quantize(PAISE) with typed=True. Frontend (21c check): 'Your price 81.30', 'typed 24 Oct 2026, 10:35:12 IST'; the price is sent as text.
attack: Removing the tick check from set_typed_price (M3b) failed test_typed_price_off_tick_is_refused_and_on_tick_is_marked_typed, which also asserts the typed mark. 21c number and label mutants were killed.

Recorded by the orchestrator from the verifier's returned block.
