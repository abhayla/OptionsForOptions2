---
work_item: W-200
requirement: REQ-046
ac: AC-5
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "75dd513aaefe"
commands: "read TrackingPanel.vue:109-113; read tracking.js:119-123; grep -i 'as of|data state|timestamp' drawer and compare files"
---
Not verified in budget. Seen: the drawer's 'Why detected' lines carry index, distance, threshold and 'As of <IST time>'. Not seen: a data state (live, paused, stale) inside the explanation; paused/not-connected text exists only in the tracking panel header (tracking.js:50-53, 126-127); no test asserts a data state in the explanation.

To close: confirm whether the drawer or a FigureHint carries the data state, and test it.

Recorded by the orchestrator from the verifier's returned block.
