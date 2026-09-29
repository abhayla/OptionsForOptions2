---
work_item: W-021
ac: AC-7
result: pass
verified_by: "verifier (opus, fresh context; rounds W-021 to W-021g)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/reconciliation/test_standalone.py; spec example script"
---

AC: AC-7
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/reconciliation/test_standalone.py; spec example script
observed: SELL 25000 CE x50 + standalone 25: broker -75 no mismatch; -50 blocks only that strategy (difference 25); a standalone is never counted as a second holder
attack: standalone sign flip and broker side flip flagged; ignore-standalone mutant killed

Recorded by the orchestrator from the verifier's returned block.
