---
work_item: W-025
ac: AC-5
result: pass
verified_by: "verifier (sonnet, fresh context; third check at ba980cf)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/range/test_pick_lists.py; independent script over tests/fixtures/instruments/instruments_slice.csv"
---

AC: AC-5
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/range/test_pick_lists.py; independent script over tests/fixtures/instruments/instruments_slice.csv
observed: independently recomputed: NIFTY 2026-09-29 lower 26 values to 20800, upper 31 to 26200; NIFTY 2026-10-06 lower 26 to 20800, upper 27 to 25800; SENSEX 2026-10-01 lower 91 to 72500, upper 18 to 83100; SENSEX 2026-10-08 lower 91 to 72500, upper 14 to 82700; every value after the first is a listed strike
attack: round 1 (my brief's default) put values between strikes (SENSEX 81,422 -> 81,322) and stopped at 20,837 short of 20,800; round 2 snapped to the grid; round 3 fixed a wrong-side final value. Independent 13-point sweep over both indices and directions: strictly monotonic, no duplicates, all listed strikes

Recorded by the orchestrator from the verifier's returned block.
