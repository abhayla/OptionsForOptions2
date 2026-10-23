---
work_item: W-144
ac: AC-4
requirement: REQ-038
ac_fp: "0efcb617bb28"
result: pass
verified_by: "independent verifiers (Opus, fresh context; round 1 on d99b2097, round 2 on 735ba1a6; DB part CI #525 on f5a1059c)"
builder: "builders (Opus, builder sequence row 16: build, fix 1)"
date: '2026-10-23'
commands: "round 1 (Opus) FAIL MAJOR (flag lost across requests); fix 1; round 2 (Opus) on 735ba1a6: fixed; DB part local 168 passed + CI #525"
---

AC: AC-4
result: pass
commands: round 1 (Opus) FAIL MAJOR (flag lost across requests); fix 1; round 2 (Opus) on 735ba1a6: fixed; DB part local 168 passed + CI #525
observed: the recorded actual is the broker share (execution_return.py:356-366); reconciliation_required persisted and replayed (strategy_store.py:420-439), PUT and confirm refused in a new request; manual same-direction units are outside lots and block nothing (ADR-109); a shortfall or side flip takes the broker's units and flags
attack: drift/undecidable mutants M1-M3 killed (scratch exec-mutation); each broker answer state (complete/match, complete/different, partial, rejected/failed with and without units, units unknown) has a test row

Recorded by the orchestrator from the verifier's returned block.
