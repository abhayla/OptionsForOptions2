---
work_item: W-004
ac: AC-2
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "same; ran build_table on the golden fixture via python -c with PYTHONPATH=backend"
---

AC: AC-2
result: pass
commands: same; ran build_table on the golden fixture via python -c with PYTHONPATH=backend
observed: Column order matches AC-2 (test_core_golden_iron_condor_column_order_matches_ac2); scenario headings 22,900 | 0-P&L 22,909 | 23,000 | CURRENT 23,047; net credit 91.0 -> BE 22909 / 23491
attack: Recomputed the breakevens independently from the premiums (86+91.5-42.5-44=91) and compared against the built headings: they matched.

Recorded by the orchestrator from the verifier's returned block.
