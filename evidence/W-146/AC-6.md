---
work_item: W-146
ac: AC-6
requirement: REQ-035
ac_fp: "f1902d3f9ef1"
result: pass
verified_by: "independent verifiers (Opus, fresh context: round 1 on 412b56c6, findings-only round 2 on ce2ab433)"
builder: "builders (earlier work items W-064; row 18 build 94077a89, Sonnet)"
date: '2026-10-24'
commands: "Opus check round 1 on 412b56c6 (verify-row-18.md): code trace model.py:257 -> ofo.engine.model.leg_greeks_unrounded; tests/table"
---

AC: AC-6
result: pass
commands: Opus check round 1 on 412b56c6 (verify-row-18.md): code trace model.py:257 -> ofo.engine.model.leg_greeks_unrounded; tests/table
observed: IV and Greeks from the platform engine; a vendor Greek only in the cell's vendor field (model.py:310, serialize.py:42)
attack: traced every Greek cell to the engine

Recorded by the orchestrator from the verifier's returned block.
