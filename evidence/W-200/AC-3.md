---
work_item: W-200
requirement: REQ-046
ac: AC-3
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "14725eb76dd3"
commands: "read backend/ofo_app/routes/adjustment.py:535-550 (_available); python (import ofo.errors.explanations and ofo.adjustment.approaches; regex over all 15 APPROACH_IDS names and ABOUT texts); cd frontend && npx vitest run tests/adjust-drawer.test.js"
---
_available returns all 15 APPROACH_IDS with name, one-line explanation, applicable and reason, and no figures. A regex for best/better/winner/rank/score/recommend/should/ideal/optimal/safest/suggest matched none of the real catalogue texts. adjust-drawer.test.js 16 passed incl. the wording test. Applicable approaches start ticked as a selection default, not labelled a recommendation.

DB proof owed: tests_app/test_adjustment_approaches_route.py (the drawer's one-read route test).

Recorded by the orchestrator from the verifier's returned block.
