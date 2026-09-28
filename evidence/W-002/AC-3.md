---
work_item: W-002
ac: AC-3
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/engine/test_black_scholes.py; BS attack script"
---

AC: AC-3
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/engine/test_black_scholes.py; BS attack script
observed: 12 passed; Hull call 4.76, put 0.81; IV from the quoted 4.76 = 0.200066 which re-prices to 4.76; _solve_iv on the unrounded price within 1e-6 of 0.20; Greeks match finite differences
attack: price below intrinsic raises NoImpliedVolatilityError; float years, NaN vol and NaN rate refused. Two verification rounds: round 1 all pass with 2 gaps (IV accepted float-built price; metrics had its own sign), fixed and re-verified.

Recorded by the orchestrator from the verifier's returned block.
