---
work_item: W-010
ac: AC-1
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/admin; python - (10k import, add/edit/remove/reactivate script)"
---

AC: AC-1
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/admin; python - (10k import, add/edit/remove/reactivate script)
observed: 10k apply added 10000 in 0.4s; lower-case, BOM, CRLF, 2-column file worked; remove sets INACTIVE (is_qualifying False, row kept in export); reactivate makes it True
attack: 7 changing methods with actor None or a plain string, and Actor('')/Actor('  '): all refused. All 8,571 independently generated bad inputs refused on add and edit. Verified after 3 rounds (round 1: upper() folded non-ASCII; round 2: strip() before isascii(); independent review; round 3 single ascii_token gate).

Recorded by the orchestrator from the verifier's returned block.
