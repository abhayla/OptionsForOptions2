---
work_item: W-147
ac: AC-7
requirement: REQ-080
ac_fp: "dbaf29839ec1"
result: pass
verified_by: "independent verifiers (Opus backend on d88a7354; Sonnet frontend on 86264455; Sonnet findings-only round 2 on 4d4b26dc)"
builder: "builders (Sonnet: backend 43b8bebb..ae0327e7, fixes 00814777/5052df89/f8501c76; frontend 5e649b2a, 4d4b26dc)"
date: '2026-10-24'
commands: "Opus backend check on d88a7354 (verify-row-19b.md; real KiteProvider replaying the 2026-10-08 recording): /depth bids=5 asks=5, day values 326.15/356.60/262.95/378.85; Sonnet frontend check on 86264455 (verify-row-19f.md; vitest mounts with leg_picker.py response shapes); Sonnet findings-only round 2 on 4d4b26dc (per-viewer lease, selection list): 1000 ms pin"
---

AC: AC-7
result: pass
commands: Opus backend check on d88a7354 (verify-row-19b.md; real KiteProvider replaying the 2026-10-08 recording): /depth bids=5 asks=5, day values 326.15/356.60/262.95/378.85; Sonnet frontend check on 86264455 (verify-row-19f.md; vitest mounts with leg_picker.py response shapes); Sonnet findings-only round 2 on 4d4b26dc (per-viewer lease, selection list): 1000 ms pin
observed: depth icon on each leg in the builder's leg list opens a popup: 5 levels with quantities, open/high/low/previous close, last trade time, read time; refresh at most once a second while open, stops on close; no order button. The icon on the strategy's own leg rows comes with row 20 (REQ-076 leg rows)
attack: mutants 'refresh at 500 ms', 'timer never cleared', 'order button added' killed

Recorded by the orchestrator from the verifier's returned block.
