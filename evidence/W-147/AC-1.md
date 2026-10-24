---
work_item: W-147
ac: AC-1
requirement: REQ-080
ac_fp: "21d6e10ef0e3"
result: pass
verified_by: "independent verifiers (Opus backend on d88a7354; Sonnet frontend on 86264455; Sonnet findings-only round 2 on 4d4b26dc)"
builder: "builders (Sonnet: backend 43b8bebb..ae0327e7, fixes 00814777/5052df89/f8501c76; frontend 5e649b2a, 4d4b26dc)"
date: '2026-10-24'
commands: "Opus backend check on d88a7354 (verify-row-19b.md; real KiteProvider replaying the 2026-10-08 recording): /strikes rows=21 atm_rows=1, widths 20/30/40 -> 41/61/81, width 15 -> 422; Sonnet frontend check on 86264455 (verify-row-19f.md; vitest mounts with leg_picker.py response shapes): tabs, widths, ATM, underlying locked"
---

AC: AC-1
result: pass
commands: Opus backend check on d88a7354 (verify-row-19b.md; real KiteProvider replaying the 2026-10-08 recording): /strikes rows=21 atm_rows=1, widths 20/30/40 -> 41/61/81, width 15 -> 422; Sonnet frontend check on 86264455 (verify-row-19f.md; vitest mounts with leg_picker.py response shapes): tabs, widths, ATM, underlying locked
observed: Strikes and Futures tabs; strikes around ATM (10 default, 10/20/30/40) with ATM highlighted, NIFTY and SENSEX
attack: width outside the set refused; two viewers on different expiries both priced on every read (round 2)

Recorded by the orchestrator from the verifier's returned block.
