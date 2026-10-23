---
work_item: W-141
ac: AC-4
requirement: REQ-032
ac_fp: "6c57050b468b"
result: pass
verified_by: "independent verifiers (Opus, fresh context; start check on f9a8d780, DB part Sonnet on fb9a3702)"
builder: "builders (earlier work items; builder sequence row 13 start check, no new code)"
date: '2026-10-23'
commands: "start check (Opus, fresh) on f9a8d780"
---

AC: AC-4
result: pass
commands: start check (Opus, fresh) on f9a8d780
observed: -322.50 exact; floats only inside black_scholes.py and forward.py (levels and a yield, Decimal at output)
attack: Decimal-exact hand computation; grep for float in money paths

Recorded by the orchestrator from the verifier's returned block.
