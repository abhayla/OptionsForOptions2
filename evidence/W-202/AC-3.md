---
work_item: W-202
requirement: REQ-155
ac: AC-3
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "c3fa873c48ca"
commands: "python -m pytest -q -p no:cacheprovider tests/adjustment/test_whole_trade.py; read whole_trade.py:115-148, adjustment.py:353-377 and 412-418"
---
paid_charges, adjustment_charges (closing plus opening orders via _trade_orders) and open_exit_charges are separate fields, carried as this_adjustment, paid_so_far and open_exit; total is subtracted once (whole_trade.py:139,146). test_ac3_each_charge_line_is_kept_apart_and_subtracted_exactly_once passes. Attack: unknown rates or paid charges withhold the after-charges figures instead of folding in 0.
