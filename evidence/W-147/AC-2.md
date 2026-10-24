---
work_item: W-147
ac: AC-2
requirement: REQ-080
ac_fp: "2e10370d9fdf"
result: pass
verified_by: "independent verifiers (Opus backend on d88a7354; Sonnet frontend on 86264455; Sonnet findings-only round 2 on 4d4b26dc)"
builder: "builders (Sonnet: backend 43b8bebb..ae0327e7, fixes 00814777/5052df89/f8501c76; frontend 5e649b2a, 4d4b26dc)"
date: '2026-10-24'
commands: "Opus backend check on d88a7354 (verify-row-19b.md; real KiteProvider replaying the 2026-10-08 recording): hand Black-Scholes on 10 NIFTY + 10 SENSEX cells vs the route; Sonnet frontend check on 86264455 (verify-row-19f.md; vitest mounts with leg_picker.py response shapes): values rendered as sent"
---

AC: AC-2
result: pass
commands: Opus backend check on d88a7354 (verify-row-19b.md; real KiteProvider replaying the 2026-10-08 recording): hand Black-Scholes on 10 NIFTY + 10 SENSEX cells vs the route; Sonnet frontend check on 86264455 (verify-row-19f.md; vitest mounts with leg_picker.py response shapes): values rendered as sent
observed: CE/PE LTP and OI from the platform feed; IV and delta from the engine (max gap IV 0.0047 points, delta 0.00005)
attack: mutants 'IV/delta computed outside the engine' killed by the replay-backed route test

Recorded by the orchestrator from the verifier's returned block.
