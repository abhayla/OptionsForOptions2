---
work_item: W-206
requirement: REQ-159
ac: AC-6
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "41d897082078"
commands: "python tools/ac_fp.py REQ-159 AC-6 --yaml; read spec/requirements/REQ-159.md"
---
Not verified in budget. Guard wiring (hide_oi_below, hide_spread, roll_debit_limit, max_adjustments, cost warning, order sequence) not traced into route or worker. REQ-159 still says the F-78 guards are 'applied nowhere yet' and 'the built checker does not do this yet (F-77)'; whether that text is stale is unconfirmed.

Follow-up: trace the guards and update or confirm the F-77/F-78 text.

Recorded by the orchestrator from the verifier's returned block.
