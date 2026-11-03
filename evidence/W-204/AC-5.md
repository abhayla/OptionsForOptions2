---
work_item: W-204
requirement: REQ-157
ac: AC-5
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "7486f558f263"
commands: "cd frontend && npx vitest run tests/adjust-compare.test.js"
---
chartLines, the table columns and the prepare picker all derive from the same kept computed (AdjustCompare.vue:246-260); pick resets when its option is filtered out (:251). Test :201 passed.

Recorded by the orchestrator from the verifier's returned block.
