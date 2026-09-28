---
work_item: W-012
ac: AC-3
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/strategy/test_versions.py; python - (sequences A/B/C + random)"
---

AC: AC-3
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/strategy/test_versions.py; python - (sequences A/B/C + random)
observed: ACTIVATED only when confirmed, pending, flag clear and actual == intended (asserted every step); a late COMPLETE matching intended while flagged -> BLOCKED; the proposal baseline equals the active intended position and never changes
attack: confirm/edit/propose/restore under the flag refused; a late result after reconcile refused

Recorded by the orchestrator from the verifier's returned block.
