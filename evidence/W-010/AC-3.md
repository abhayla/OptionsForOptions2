---
work_item: W-010
ac: AC-3
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python - search/filter script"
---

AC: AC-3
result: pass
commands: python - search/filter script
observed: search(prefix, status, linked) correct; INACTIVE filter and no-match prefix return 0
attack: every contaminant as a prefix (and its first 4 characters) raises ValueError; ASCII no-match prefix returns nothing

Recorded by the orchestrator from the verifier's returned block.
