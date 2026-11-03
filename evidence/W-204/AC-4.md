---
work_item: W-204
requirement: REQ-157
ac: AC-4
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "a528f8858f50"
commands: "cd frontend && npx vitest run tests/adjust-compare.test.js"
---
judge() records the filter name as unavailable when a value is undefined and does not hide the approach; the column header shows 'not available for this filter' (AdjustCompare.vue:90). Test :209 passed. Attack: a non-decimal value keeps the approach (fail-open in the user's favour).
