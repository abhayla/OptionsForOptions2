---
work_item: W-200
requirement: REQ-046
ac: AC-5
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 4)"
date: 2026-11-04
ac_fp: "75dd513aaefe"
commands: "read frontend/src/lib/tracking.js:40-60,100-130; read frontend/src/components/strategy/TrackingPanel.vue:35-60,100-120; read frontend/src/components/strategy/AdjustDrawer.vue:18-20; read backend/ofo_app/routes/tracking.py:300-320; grep adjustment_detection frontend/src; cd frontend && npx vitest run tests/tracking.test.js"
---
tracking.js:127 builds the explanation details as only [Index, Distance, Threshold, 'As of <IST>']: the timestamp is there, the data state (live / paused / stale) is not. The drawer prints the same lines (TrackingPanel.vue:104-107, AdjustDrawer.vue:20). The server sends price_health (tracking.py:318) but nothing in frontend/src reads it; paused text appears only in the panel header (tracking.js:50-53,126). tracking.test.js (19 pass) pins details to exactly those 4 lines. Attack: a paused or stale answer with a detection gives an explanation with no state word.

Fix: a data-state line from price_health in the details.

Recorded by the orchestrator from the verifier's returned block.
