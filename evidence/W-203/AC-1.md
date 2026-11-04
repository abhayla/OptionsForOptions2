---
work_item: W-203
requirement: REQ-156
ac: AC-1
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 4)"
date: 2026-11-04
ac_fp: "858214d6c16c"
commands: "read backend/ofo_app/routes/adjustment.py:440-490; read spec/requirements/REQ-156.md AC-1 and REQ-155.md AC-5; read frontend/src/components/strategy/AdjustCompare.vue:229-285; read frontend/src/lib/adjustCompare.js:97-101; cd frontend && npx vitest run tests/adjust-compare.test.js"
---
REQ-156 AC-1: the compare 'always' lists 'No change'. adjustment.py:468-470 (if not spot.available) returns before=None and approaches=[]; tableApproaches (adjustCompare.js:97) then has nothing, so the page shows only 'Spot not available' (AdjustCompare.vue:277-279) and no No-change row. adjust-compare.test.js 25/25 has no no-spot case. Attack: every spot source failed -> No change missing, against 'always'.

Conflict with REQ-155 AC-5 ('no After is computed'): reconcile in REQ-156 AC-1 or return a Before-only No-change row.

Recorded by the orchestrator from the verifier's returned block.
