---
work_item: W-210
requirement: REQ-163
ac: AC-1
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "000fc036a329"
commands: "read backend/ofo_app/routes/adjustment_history.py; read backend/ofo/engine/adjust_history.py"
---
Rows carry time, orders, cash, booked P&L, charges and the paper fill text. But the route builds HistoryOrder without rule_id and without fill (adjustment_history.py:211-216), so 'why it was made' is always 'Your own change' and the opportunity is never shown; the docstring (lines 17-18) says no suggestion link is stored. Every row is fixed to the 'paper' fill state, so no REQ-112 AC-3 fill state can appear.

Fix at adjustment_history.py:211-216 (pass the suggestion rule_id and the fill state). DB proof owed: tests_app/test_adjustment_history.py::test_adj13_history_rows_and_totals_equal_the_domain_and_the_generator.
