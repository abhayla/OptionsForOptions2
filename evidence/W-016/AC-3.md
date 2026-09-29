---
work_item: W-016
ac: AC-3
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "same pytest; attack script"
---

AC: AC-3
result: pass
commands: same pytest; attack script
observed: restoring each of 6 entries gives exactly that entry's legs; the pre-restore configuration is saved first; restore(0/-1/len+1/'1'/True/1.0/None/Decimal(1)) refused
attack: restore of every entry, out-of-range and wrong-type values

Recorded by the orchestrator from the verifier's returned block.
