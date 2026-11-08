---
work_item: W-200
requirement: REQ-046
ac: AC-1
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "60b9bcd828da"
commands: "read frontend/src/lib/tracking.js; read frontend/src/components/strategy/TrackingPanel.vue; cd frontend && npx vitest run tests/tracking.test.js"
---
tracking.js:122-123: d.line = label + condition + strike/breakeven + distance as one visible line; d.details = Index, Distance, Threshold, As of <IST time> behind FigureHint. tracking.test.js 19 passed; a test asserts the exact line and that Threshold/As of/index stay hidden until the '?' is opened. Attack 'no detection': detections [] renders no detection row and hides the review button.

Held in both attacks.

Recorded by the orchestrator from the verifier's returned block.
