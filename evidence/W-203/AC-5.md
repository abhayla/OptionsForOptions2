---
work_item: W-203
requirement: REQ-156
ac: AC-5
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "4c3c92095255"
commands: "cd frontend && npx vitest run tests/adjust-compare.test.js"
---
AdjustPayoffChart.vue draws one dataset per line with borderDash for Before; one legend button per line with aria-pressed toggles hiddenLines. Test :117 (Before dashed, own lines, hiding removes only that line) passed.

Canvas pixels not inspected.
