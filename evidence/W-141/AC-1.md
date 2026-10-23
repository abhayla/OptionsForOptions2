---
work_item: W-141
ac: AC-1
requirement: REQ-032
ac_fp: "6810bcbee732"
result: pass
verified_by: "independent verifiers (Opus, fresh context; start check on f9a8d780, DB part Sonnet on fb9a3702)"
builder: "builders (earlier work items; builder sequence row 13 start check, no new code)"
date: '2026-10-23'
commands: "start check (Opus, fresh) on f9a8d780, results-rows-12-14.md; tests/engine 724, tests/scenario 38 passed"
---

AC: AC-1
result: pass
commands: start check (Opus, fresh) on f9a8d780, results-rows-12-14.md; tests/engine 724, tests/scenario 38 passed
observed: table, payoff and summary from one scenario_values call (service.py:469); only math outside the engine is marketdata/forward.py (q, an engine input per ADR-063); PayoffChart.vue only Number() for plotting
attack: grep for P&L math outside the engine; 24 mutants (21 killed)

Recorded by the orchestrator from the verifier's returned block.
