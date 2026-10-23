---
work_item: W-147
ac: AC-3
requirement: REQ-080
ac_fp: "8d40bcd4d3e9"
result: pass
verified_by: "independent verifiers (Opus backend on d88a7354; Sonnet frontend on 86264455; Sonnet findings-only round 2 on 4d4b26dc)"
builder: "builders (Sonnet: backend 43b8bebb..ae0327e7, fixes 00814777/5052df89/f8501c76; frontend 5e649b2a, 4d4b26dc)"
date: '2026-10-24'
commands: "Sonnet frontend check on 86264455 (verify-row-19f.md; vitest mounts with leg_picker.py response shapes); Sonnet findings-only round 2 on 4d4b26dc (per-viewer lease, selection list): vitest leg-picker 60 passed"
---

AC: AC-3
result: pass
commands: Sonnet frontend check on 86264455 (verify-row-19f.md; vitest mounts with leg_picker.py response shapes); Sonnet findings-only round 2 on 4d4b26dc (per-viewer lease, selection list): vitest leg-picker 60 passed
observed: Buy/Sell and lots per cell; several selected; a visible selection list with Remove; Done adds exactly that list, each through the planned-entry capture; no order call
attack: mutants 'refresh clears the selection' and 'unpick does nothing' killed; Done with nothing selected sends no request

Recorded by the orchestrator from the verifier's returned block.
