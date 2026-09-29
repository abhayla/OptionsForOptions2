---
work_item: W-016
ac: AC-1
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/strategy/test_builder_history.py; attack script"
---

AC: AC-1
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/strategy/test_builder_history.py; attack script
observed: 29 passed; alternatives differing in quantity, expiry or BUY/SELL record 'Setup changed to alternative'; a reordered identical alternative records nothing; original setup preserved as entry 1
attack: duplicate-leg alternatives refused with history unchanged. Note (deferred #10): an alternative differing only in LTP records an entry. Verified after 3 rounds (round 1: entries held the pre-change snapshot under the change's label; round 2: order-sensitive no-op check; round 3 pass).

Recorded by the orchestrator from the verifier's returned block.
