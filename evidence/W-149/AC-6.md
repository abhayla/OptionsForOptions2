---
work_item: W-149
ac: AC-6
requirement: REQ-077
ac_fp: "0dd520cf1d19"
result: pass
verified_by: "independent verifiers (Opus part checks 21m/21b/21a/21d with round 2; Sonnet 21c check + round 2; Opus CI-fix check + round 2; Opus row 21 closing check on 9730cda2)"
builder: "builders (Opus: 21m 8a3bf0d2, 21b 8f5dc56e, 21a c851c84d, 21d 6d4ae53f; Sonnet: 21c f1a5e938 + fix 264576bb, CI fix 6bac88cf..ab38cd8d)"
date: '2026-10-24'
commands: "vitest (strategy-live, leg-edit) and app runs as above"
---

AC: AC-6
result: pass
commands: vitest (strategy-live, leg-edit) and app runs as above
observed: The marker is display only: 'Price has moved since <time>: planned 44.90, now 47.15' by string comparison, no browser arithmetic. The backend computes numbers only from the planned entries sent (leg_edit.py:396); no path writes the live LTP into planned_entry except reset_prices / reset_leg / a stepped leg.
attack: 21c mutants (equality check removed, no-live check removed) killed; FROM_ENTRIES legs carry no ltp, so no marker there.

Recorded by the orchestrator from the verifier's returned block.
