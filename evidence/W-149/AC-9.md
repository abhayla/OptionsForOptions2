---
work_item: W-149
ac: AC-9
requirement: REQ-077
ac_fp: "a1a73017f00d"
result: pass
verified_by: "independent verifiers (Opus part checks 21m/21b/21a/21d with round 2; Sonnet 21c check + round 2; Opus CI-fix check + round 2; Opus row 21 closing check on 9730cda2)"
builder: "builders (Opus: 21m 8a3bf0d2, 21b 8f5dc56e, 21a c851c84d, 21d 6d4ae53f; Sonnet: 21c f1a5e938 + fix 264576bb, CI fix 6bac88cf..ab38cd8d)"
date: '2026-10-24'
commands: "python -m pytest -q -p no:cacheprovider tests/outcome tests/engine; app run incl. test_outcome_route.py, test_strategy_live_push.py; mutants M7 (output_label), M8 (any-leg-unpriced guard, service.py:396), M11 (buildDraft unpriced guard) with npx vitest run tests/leg-picker.test.js tests/leg-edit.test.js; CI App tests run 40063948683 green on 9730cda2 incl. the e2e live-strategy specs"
---

AC: AC-9
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/outcome tests/engine; app run incl. test_outcome_route.py, test_strategy_live_push.py; mutants M7 (output_label), M8 (any-leg-unpriced guard, service.py:396), M11 (buildDraft unpriced guard) with npx vitest run tests/leg-picker.test.js tests/leg-edit.test.js; CI App tests run 40063948683 green on 9730cda2 incl. the e2e live-strategy specs
observed: service.py:386-451 from_entries: no ltp/iv/health/spot, At Expiry from the engine, Estimated Now unavailable with its reason; status_label is REQ-049 AC-5's message when a quote was held, else 'From your prices - no live data'; an ended session goes to from_entries; leg_quotes only for COMPUTED. Screens: Builder shows both labels, the Live Strategies card both labels and paused, a FROM_ENTRIES push is never live; buildDraft sends nothing when any included leg is unpriced.
attack: M7: 1 failed; M8: 3 failed, 13 passed; M11: 3 failed, 92 passed. Dropped feed and ended session tests pass.

Recorded by the orchestrator from the verifier's returned block.
