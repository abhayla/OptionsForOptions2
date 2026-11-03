---
work_item: W-204
requirement: REQ-157
ac: AC-2
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "1cb4f5f89e9f"
commands: "cd frontend && npx vitest run tests/adjust-compare.test.js"
---
buildFacets() derives kinds and sides only from the non-No-change, non-refused approaches in the reply; range ends are the min and max present (spanOf); no fixed list apart from display order. A watch drops choices no longer offered (AdjustCompare.vue:238). Test :158 passed.

Recomputation only on reload or scope change; not exercised in a test.
