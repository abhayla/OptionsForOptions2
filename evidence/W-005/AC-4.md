---
work_item: W-005
ac: AC-4
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus), round 3 (fresh builder)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/strategy/test_strategy_model.py; python - (exhaustive sweep, near-miss and fuzz)"
---

AC: AC-4
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/strategy/test_strategy_model.py; python - (exhaustive sweep, near-miss and fuzz)
observed: exhaustive 48,345 parameter points: 0 bad, no ambiguity; 4,000 round trips: 0 bad; fuzz 60,000: 2,154 matched, 0 wrong, 0 exceptions
attack: 23,470 near misses (BUY/SELL flip, CE<->PE, one-step shift, extra/dropped leg, 2:1 quantity): every match rebuilds exactly to the variant's real shape; none mislabelled; unequal-wing condor/butterfly -> Custom; off-grid strike -> Custom

Recorded by the orchestrator from the verifier's returned block.
