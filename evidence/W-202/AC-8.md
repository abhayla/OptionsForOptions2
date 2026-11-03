---
work_item: W-202
requirement: REQ-155
ac: AC-8
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "d5cd85a2a274"
commands: "python -m pytest -q -p no:cacheprovider tests/adjustment/test_approaches.py; read approaches.py:342-357"
---
open() refuses a new leg on an unlisted or untradable row, a low-OI blocked row and a row with no price, and only warns when low OI is unknown; every refusal names the leg. test_ac8_every_answer_state_of_the_landing_row covers all four states; the ADJ-20d test shows only A-05 refused for an unlisted 23,700 CE while the rest still build. applicable_approaches never drops a refused approach.
