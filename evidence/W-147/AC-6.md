---
work_item: W-147
ac: AC-6
requirement: REQ-080
ac_fp: "98a6d09fd879"
result: pass
verified_by: "independent verifiers (Opus backend on d88a7354; Sonnet frontend on 86264455; Sonnet findings-only round 2 on 4d4b26dc)"
builder: "builders (Sonnet: backend 43b8bebb..ae0327e7, fixes 00814777/5052df89/f8501c76; frontend 5e649b2a, 4d4b26dc)"
date: '2026-10-24'
commands: "Opus backend check on d88a7354 (verify-row-19b.md; real KiteProvider replaying the 2026-10-08 recording): /futures forward NIFTY ('2026-10-13','22529.17','parity'), SENSEX parity; Sonnet frontend check on 86264455 (verify-row-19f.md; vitest mounts with leg_picker.py response shapes): 'Forward used for pricing'"
---

AC: AC-6
result: pass
commands: Opus backend check on d88a7354 (verify-row-19b.md; real KiteProvider replaying the 2026-10-08 recording): /futures forward NIFTY ('2026-10-13','22529.17','parity'), SENSEX parity; Sonnet frontend check on 86264455 (verify-row-19f.md; vitest mounts with leg_picker.py response shapes): 'Forward used for pricing'
observed: per option expiry the forward the engine prices with (parity or labelled spot fallback); futures listed with LTP or reason. Live check pending (row 63): the futures LTP itself - the recording has no futures rows or tick; proven only on a relabelled real option packet
attack: futures reasons NO_QUOTE / FEED_STALE / NOT_STREAMABLE / NOT_OFFERED each rendered

Recorded by the orchestrator from the verifier's returned block.
