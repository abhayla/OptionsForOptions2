---
work_item: W-149
ac: AC-2
requirement: REQ-077
ac_fp: "643751b2afa8"
result: pass
verified_by: "independent verifiers (Opus part checks 21m/21b/21a/21d with round 2; Sonnet 21c check + round 2; Opus CI-fix check + round 2; Opus row 21 closing check on 9730cda2)"
builder: "builders (Opus: 21m 8a3bf0d2, 21b 8f5dc56e, 21a c851c84d, 21d 6d4ae53f; Sonnet: 21c f1a5e938 + fix 264576bb, CI fix 6bac88cf..ab38cd8d)"
date: '2026-10-24'
commands: "same app and vitest runs; mutants M3 (tests/strategy/test_leg_edit.py) and M3b (tests_app/test_leg_edit_route.py): drop the round_to_tick check"
---

AC: AC-2
result: pass
commands: same app and vitest runs; mutants M3 (tests/strategy/test_leg_edit.py) and M3b (tests_app/test_leg_edit_route.py): drop the round_to_tick check
observed: set_typed_price (ofo/strategy/leg_edit.py:163-167) reads the tick from the instrument file and refuses None, text, a float, <=0, more than 2 decimals or off-tick with leg_edit_price_not_tick = USER_INPUT_013 (four parts, ofo/errors/templates.py:975); legs are returned unchanged on refusal. Frontend: the error shows under that leg's field and the previous price stays.
attack: M3: 1 failed, 7 passed. M3b: 1 failed, 11 passed. 21c error-index mutant killed.

Recorded by the orchestrator from the verifier's returned block.
