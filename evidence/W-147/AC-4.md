---
work_item: W-147
ac: AC-4
requirement: REQ-080
ac_fp: "9a8855f7cf9b"
result: pass
verified_by: "independent verifiers (Opus backend on d88a7354; Sonnet frontend on 86264455; Sonnet findings-only round 2 on 4d4b26dc)"
builder: "builders (Sonnet: backend 43b8bebb..ae0327e7, fixes 00814777/5052df89/f8501c76; frontend 5e649b2a, 4d4b26dc)"
date: '2026-10-24'
commands: "Sonnet frontend check on 86264455 (verify-row-19f.md; vitest mounts with leg_picker.py response shapes): SENSEX lot 20 -> 20..200 in quantity mode"
---

AC: AC-4
result: pass
commands: Sonnet frontend check on 86264455 (verify-row-19f.md; vitest mounts with leg_picker.py response shapes): SENSEX lot 20 -> 20..200 in quantity mode
observed: Lots/Quantity setting for every user; quantity lists multiples of the lot size from the server data; lots lists 1, 2, 3
attack: mutant 'typed 65 lot size' killed

Recorded by the orchestrator from the verifier's returned block.
