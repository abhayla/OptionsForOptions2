---
work_item: W-203
requirement: REQ-156
ac: AC-2
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "9eb6a536d6a2"
commands: "python -m pytest -q -p no:cacheprovider tests/adjustment/test_approach_compare.py tests/adjustment/test_compare_cost_rows.py; cd frontend && npx vitest run tests/adjust-compare.test.js"
---
compare.py:83-92 ROWS covers all five groups with the move rows from the user's view; an import-time check ties ROWS to the catalogue labels (compare.py:101). Every number comes from whole_trade_after, Strategy.expiry_pnl_at and the charges calculator. Attack: no browser-side P&L (adjustCompare.js compares decimal texts only).

Default move percents not re-checked.
