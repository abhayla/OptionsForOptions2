---
work_item: W-016
ac: AC-5
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "same pytest; attack script"
---

AC: AC-5
result: pass
commands: same pytest; attack script
observed: after mark_executed all 11 mutators refused; history readable; public attributes read-only; default_view has only legs, display_name, display_flags (a copy)
attack: every edit path after execution, direct attribute writes, flags-mapping mutation, history leak through default_view

Recorded by the orchestrator from the verifier's returned block.
