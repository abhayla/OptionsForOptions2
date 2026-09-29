---
work_item: W-025
ac: AC-3
result: pass
verified_by: "verifier (sonnet, fresh context; third check at ba980cf)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/range/test_pick_lists.py"
---

AC: AC-3
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/range/test_pick_lists.py
observed: 38 passed; both lists always start at the exact current level, once (also on a 100-multiple); no default range is ever pre-filled
attack: current on the grid (23200), current beyond every strike (100000), current below every strike: first value is current_level in every case

Recorded by the orchestrator from the verifier's returned block.
