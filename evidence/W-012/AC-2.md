---
work_item: W-012
ac: AC-2
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/strategy/test_versions.py; python - (own random test, seed 424242, 1,500 sequences)"
---

AC: AC-2
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/strategy/test_versions.py; python - (own random test, seed 424242, 1,500 sequences)
observed: 30 passed; edits before execution are history entries; after execution each meaningful edit is a new frozen version; earlier versions unchanged across 26,051 steps
attack: assigning to a version raises FrozenInstanceError; restore under the reconciliation flag refused; a first execution REJECTED with nothing filled keeps history mode

Recorded by the orchestrator from the verifier's returned block.
