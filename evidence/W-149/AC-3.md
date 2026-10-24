---
work_item: W-149
ac: AC-3
requirement: REQ-077
ac_fp: "1edbc339694d"
result: pass
verified_by: "independent verifiers (Opus part checks 21m/21b/21a/21d with round 2; Sonnet 21c check + round 2; Opus CI-fix check + round 2; Opus row 21 closing check on 9730cda2)"
builder: "builders (Opus: 21m 8a3bf0d2, 21b 8f5dc56e, 21a c851c84d, 21d 6d4ae53f; Sonnet: 21c f1a5e938 + fix 264576bb, CI fix 6bac88cf..ab38cd8d)"
date: '2026-10-24'
commands: "python -m pytest -q -p no:cacheprovider tests/outcome tests/engine; app run incl. tests_app/test_outcome_route.py and test_leg_edit_route.py; mutant M5 routes/leg_edit.py:396 (outcome from the pre-edit legs)"
---

AC: AC-3
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/outcome tests/engine; app run incl. tests_app/test_outcome_route.py and test_leg_edit_route.py; mutant M5 routes/leg_edit.py:396 (outcome from the pre-edit legs)
observed: 846 passed. Recomputed: (81.30-30.00) x 65 = 3334.50 net debit; max profit (200-51.30) x 65 = 9665.50. tests/outcome/test_from_entries.py:56-60 asserts max_loss 3334.50 through build_outcome; tests_app/test_outcome_route.py:228,257,272 asserts '3334.50' / '9665.50' from the route; the leg-edit route builds its outcome from the typed entry with charges via rates (ADR-082).
attack: M5 failed test_leg_edit_route. Breakeven and charges use the same engine path (scenario_values / strategy_metrics), checked by reading.

Recorded by the orchestrator from the verifier's returned block.
