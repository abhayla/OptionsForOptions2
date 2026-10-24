---
work_item: W-147
ac: AC-5
requirement: REQ-080
ac_fp: "0b7cbc5a72eb"
result: pass
verified_by: "independent verifiers (Opus backend on d88a7354; Sonnet frontend on 86264455; Sonnet findings-only round 2 on 4d4b26dc)"
builder: "builders (Sonnet: backend 43b8bebb..ae0327e7, fixes 00814777/5052df89/f8501c76; frontend 5e649b2a, 4d4b26dc)"
date: '2026-10-24'
commands: "Opus backend check on d88a7354 (verify-row-19b.md; real KiteProvider replaying the 2026-10-08 recording): stale-quote, stale-spot, middle-strike and no-feed tests; Sonnet frontend check on 86264455 (verify-row-19f.md; vitest mounts with leg_picker.py response shapes)"
---

AC: AC-5
result: pass
commands: Opus backend check on d88a7354 (verify-row-19b.md; real KiteProvider replaying the 2026-10-08 recording): stale-quote, stale-spot, middle-strike and no-feed tests; Sonnet frontend check on 86264455 (verify-row-19f.md; vitest mounts with leg_picker.py response shapes)
observed: without live data strikes are still listed (centre live spot / last known spot / middle strike, labelled) with '-' and the reason; no stale price as current; reprice prompt on an unpriced leg
attack: mutants 'stale price as current' and 'stale spot as live' killed

Recorded by the orchestrator from the verifier's returned block.
