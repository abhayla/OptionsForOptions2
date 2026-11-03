---
work_item: W-202
requirement: REQ-155
ac: AC-2
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "3942cb7eb139"
commands: "python -m pytest -q -p no:cacheprovider tests/adjustment tests/marketdata/test_spot_source.py tests/engine/test_pop_paise_levels.py tests/engine/test_loss_regions_subpaisa_gap.py; read backend/ofo/engine/whole_trade.py; read backend/ofo_app/routes/adjustment.py:353-405"
---
912 passed. Booked P&L enters as a flat shift through breakevens_with_shift, loss_regions_after_charges and POP's charges=total-booked (whole_trade.py:143-148); priced_approach adds closed legs' booked P&L via adjust_money.closed_booked (adjustment.py:403). test_ac2_booked_plus_1200_lowers_max_loss_by_exactly_1200 passes. Attack: a booked loss beyond the open legs' max profit gives a negative max profit with no sign flip; an unreadable booked P&L gives no After and a reason, never 0.

Recorded by the orchestrator from the verifier's returned block.
