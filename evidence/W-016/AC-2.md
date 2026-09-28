---
work_item: W-016
ac: AC-2
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "same pytest; attack script"
---

AC: AC-2
result: pass
commands: same pytest; attack script
observed: post-change snapshots correct for strike 23050, qty 150, expiry 2026-11-03, add, remove; labels in exact order; A->B->A gives 2 strike entries; reorder/rename/toggle and same-value edits give none; 1000 mixed edits in 0.015 s
attack: snapshot-vs-label mismatch for every change type, round trip, cosmetic edits, float strike / bool qty / qty 0 refused

Recorded by the orchestrator from the verifier's returned block.
