---
work_item: W-147
ac: AC-8
requirement: REQ-080
ac_fp: "48a64bbbbb4d"
result: pass
verified_by: "independent verifiers (Opus backend on d88a7354; Sonnet frontend on 86264455; Sonnet findings-only round 2 on 4d4b26dc)"
builder: "builders (Sonnet: backend 43b8bebb..ae0327e7, fixes 00814777/5052df89/f8501c76; frontend 5e649b2a, 4d4b26dc)"
date: '2026-10-24'
commands: "Opus backend check on d88a7354 (verify-row-19b.md; real KiteProvider replaying the 2026-10-08 recording): NOT_AVAILABLE:NO_DEPTH_RECEIVED on 9 reads, never an empty table on 86 reads; Sonnet frontend check on 86264455 (verify-row-19f.md; vitest mounts with leg_picker.py response shapes)"
---

AC: AC-8
result: pass
commands: Opus backend check on d88a7354 (verify-row-19b.md; real KiteProvider replaying the 2026-10-08 recording): NOT_AVAILABLE:NO_DEPTH_RECEIVED on 9 reads, never an empty table on 86 reads; Sonnet frontend check on 86264455 (verify-row-19f.md; vitest mounts with leg_picker.py response shapes)
observed: depth unreadable (no session, stale feed, not streaming, empty or zero levels) -> 'Depth not available' with the reason; a failed refresh removes the old table; day stats unavailable carries its own reason
attack: mutants 'keep the old table on a failed refresh', 'empty-depth check removed', 'day stats null without reason' killed

Recorded by the orchestrator from the verifier's returned block.
