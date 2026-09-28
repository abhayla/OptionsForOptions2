---
work_item: W-016
ac: AC-4
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "same pytest; attack script"
---

AC: AC-4
result: pass
commands: same pytest; attack script
observed: undo right after a meaningful change returns the previous state and is recorded; second undo refused; undo after restore or a cosmetic-only edit refused; after two changes undo reverts only the last
attack: double undo, undo after restore, undo interleaved with a cosmetic change

Recorded by the orchestrator from the verifier's returned block.
