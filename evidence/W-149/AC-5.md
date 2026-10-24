---
work_item: W-149
ac: AC-5
requirement: REQ-077
ac_fp: "cee37ae76c4e"
result: pass
verified_by: "independent verifiers (Opus part checks 21m/21b/21a/21d with round 2; Sonnet 21c check + round 2; Opus CI-fix check + round 2; Opus row 21 closing check on 9730cda2)"
builder: "builders (Opus: 21m 8a3bf0d2, 21b 8f5dc56e, 21a c851c84d, 21d 6d4ae53f; Sonnet: 21c f1a5e938 + fix 264576bb, CI fix 6bac88cf..ab38cd8d)"
date: '2026-10-24'
commands: "vitest and app runs as above; mutant M4 with_entries keeps the typed mark; 21c round 2 (orchestrator) on 264576bb: reset_leg index hard-coded 0 -> 1 failed, 43 passed"
---

AC: AC-5
result: pass
commands: vitest and app runs as above; mutant M4 with_entries keeps the typed mark; 21c round 2 (orchestrator) on 264576bb: reset_leg index hard-coded 0 -> 1 failed, 43 passed
observed: routes/leg_edit.py:317-318 reset_prices marks every leg, reset_leg only its index; one capture call gives one valuation time; with_entries clears typed; a leg with no live price becomes unpriced with reason not_connected / no_live_price, never the old price. Frontend: Reset Prices and a per-leg reset on row 1 touch the right rows.
attack: M4: 1 failed, 20 passed (test_ac_5_reset_prices_recaptures_every_leg_with_one_new_time_and_clears_every_typed_mark). The per-leg index mutant is killed.

Recorded by the orchestrator from the verifier's returned block.
