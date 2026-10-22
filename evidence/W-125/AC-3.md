---
work_item: W-125
ac: AC-3
requirement: REQ-079
ac_fp: "39518ac2cffb"
result: pass
verified_by: "independent Tier A verifier (Opus, fresh context)"
builder: "builder (Sonnet, lane B cluster B4)"
date: '2026-10-22'
commands: "pytest tests/strategy/test_placement.py; verifier attack.py on instruments_slice.csv; verified sha 0f1704039dbe4f6e471c64e20776ef96e85f8404"
---

AC: AC-3
result: pass
commands: pytest tests/strategy/test_placement.py; verifier attack.py on instruments_slice.csv; verified sha 0f1704039dbe4f6e471c64e20776ef96e85f8404
observed: NIFTY 22810 -> BUY 22800 CE / SELL 23000 CE; ties take the lower strike; matches Sensibull preset-matrix 200/400-point widths
attack: spots 22825, 22824.99, 22775; tie-takes-upper mutation turned 1 test red

Recorded by the orchestrator from the verifier's returned block.
