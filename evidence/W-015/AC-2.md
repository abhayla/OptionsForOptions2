---
work_item: W-015
ac: AC-2
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/audit/test_log.py; python -m pytest -q -p no:cacheprovider tests/audit; attack script"
---

AC: AC-2
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/audit/test_log.py; python -m pytest -q -p no:cacheprovider tests/audit; attack script
observed: 22 passed; tests/audit 41 passed; no update/delete API; events is a tuple; middle deletion, reorder, swap, in-place edits rejected; tail truncation and full deletion rejected against the head anchor; append after the anchor verifies; forged chain with a stale anchor rejected; wrong anchors rejected; caller and returned payload mutation blocked; Decimal/datetime tags distinct; '$' keys reserved at any depth; naive datetimes rejected; Zerodha-order-like payload stored unchanged; 10,000 appends 1.09 s, verify 0.43 s
attack: Known limits (documented, not fails): without the separately stored anchor, tail truncation and a rebuilt chain are not detectable (unkeyed hash chain) — the anchor store is not built; a timezone-only change of the same instant is not detected (UTC hashing); timeline records belong to REQ-040 (not built), so REQ-064 is not marked Verified on W-015 alone; secret filtering is REQ-063 AC-5 (W-017, blocked).

Recorded by the orchestrator from the verifier's returned block.
