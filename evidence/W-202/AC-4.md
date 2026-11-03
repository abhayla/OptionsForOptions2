---
work_item: W-202
requirement: REQ-155
ac: AC-4
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "bced05fb1c21"
commands: "python -m pytest -q -p no:cacheprovider tests/engine/test_pop_paise_levels.py tests/engine/test_loss_regions_subpaisa_gap.py; read backend/ofo/engine/pop.py"
---
test_ac4_f75_level_22771_372_becomes_22771_37_at_the_producer passes; rounding is half-even to 0.01; pop.py:60-66 turns NaN/Infinity vol, years or forward into a named Unavailable reason; the route's pop_block shows 'POP not available' with the reason (adjustment.py:273-283). Property test of non-round prices and charges passes.

_to_decimal read by grep and docstring only.
