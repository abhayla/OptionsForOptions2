---
work_item: W-021
ac: AC-2
result: pass
verified_by: "verifier (opus, fresh context; rounds W-021 to W-021g)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/reconciliation/test_compare.py; attack scripts"
---

AC: AC-2
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/reconciliation/test_compare.py; attack scripts
observed: side, strike, expiry and quantity mismatches, missing platform position, unexpected broker position, external modification and partial execution detected; a differing shared contract lists every active or proposal holder
attack: sign flip, strike move, expiry move, non-lot quantity, standalone on the same contract; M20 (proposal holders) killed

Recorded by the orchestrator from the verifier's returned block.
