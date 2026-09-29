---
work_item: W-018
ac: AC-6
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/marketdata/test_health.py; python -c attacks"
---

AC: AC-6
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/marketdata/test_health.py; python -c attacks
observed: backend half: MonitoringStatus is a separate enum from the ADR-010 colours; per-strategy status independent. UI half (badge, grey dot, lock icon) NOT built here; it belongs to the UI work item
attack: NIFTY fresh + SENSEX stale -> ACTIVE/PAUSED split matches the AC-6 example

Recorded by the orchestrator from the verifier's returned block.
