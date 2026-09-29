---
work_item: W-025
ac: AC-6
result: pass
verified_by: "verifier (sonnet, fresh context; third check at ba980cf)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/range/test_pick_lists.py (beyond-every-strike, reviewer repro, furthest-strike and property tests); independent script"
---

AC: AC-6
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/range/test_pick_lists.py (beyond-every-strike, reviewer repro, furthest-strike and property tests); independent script
observed: current 100000 with strikes 20000-21000 -> upper [100000], lower [100000] (was [100000, 21000]); current at the furthest strike -> [current]; builder's 37-point sweep (>500 levels) and verifier's 13-point sweep hold; a fail-closed monotonic assertion backs the side guard
attack: mutations (drop side guard: 5 failed; drop monotonic assertion: 1 failed) reported by the builder; verifier reproduced the original bug scenario from scratch and the boundary cases

Recorded by the orchestrator from the verifier's returned block.
