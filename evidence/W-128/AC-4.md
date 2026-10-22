---
work_item: W-128
ac: AC-4
requirement: REQ-082
ac_fp: "34897d409e47"
result: pass
verified_by: "independent Tier A verifier (Opus, fresh context)"
builder: "builder (Sonnet, lane B cluster B4)"
date: '2026-10-22'
commands: "pytest tests/engine/test_pop.py; verifier independent erfc calculation; verified sha 0f1704039dbe4f6e471c64e20776ef96e85f8404"
---

AC: AC-4
result: pass
commands: pytest tests/engine/test_pop.py; verifier independent erfc calculation; verified sha 0f1704039dbe4f6e471c64e20776ef96e85f8404
observed: sold put 0.76216470 vs engine 0.762164700; iron condor gap 3e-8 pp (also with 130 rupees of charges)
attack: drift-sign mutation turned 5 red; dropped-charges mutation turned 1 red

Recorded by the orchestrator from the verifier's returned block.
