---
work_item: W-205
requirement: REQ-158
ac: AC-7
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "e654b1572bf4"
commands: "python (compare the ic body with docs/research/adjustments-catalogue-2026-10-30.md ids); grep -n 'T-10c|T-17|S-08|S-09' docs/research/adjustments-catalogue-2026-10-30.md"
---
ic approaches.greyed holds A-09 (Add wings) with reason 'Loss already capped'; every catalogue A-id is in the ic applicable, greyed or off lists. Gap: catalogue ids T-10, T-10c, T-17, S-08 and S-09 have no entry by id in the ic triggers or situations; T-17, S-08 and S-09 may map to the day rules (event, beforeWeekend, beforeHoliday; scenarios ADJ-15/16/18), but T-10c and T-10 (the DTE form) are unconfirmed, so 'no item dropped' cannot be confirmed.

Needs a catalogue-id -> ic body mapping test.

Recorded by the orchestrator from the verifier's returned block.
