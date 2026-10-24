---
work_item: W-146
ac: AC-2
requirement: REQ-035
ac_fp: "8988f7e2a437"
result: pass
verified_by: "independent verifiers (Opus, fresh context: round 1 on 412b56c6, findings-only round 2 on ce2ab433)"
builder: "builders (earlier work items W-064; row 18 build 94077a89, Sonnet)"
date: '2026-10-24'
commands: "Opus check round 1 on 412b56c6 (verify-row-18.md): pytest tests/table tests/outcome 141 passed; Opus findings-only round 2 on ce2ab433 (fix 94077a89): vitest strategy-table 21 passed"
---

AC: AC-2
result: pass
commands: Opus check round 1 on 412b56c6 (verify-row-18.md): pytest tests/table tests/outcome 141 passed; Opus findings-only round 2 on ce2ab433 (fix 94077a89): vitest strategy-table 21 passed
observed: route columns in the exact AC-2 order (fixture ids); rendered header order asserted in vitest since the fix
attack: mutant 'swap IV and Delta in LEADING_COLUMNS' killed by 5 tests; mutant 'swap two rendered columns' killed (round 2)

Recorded by the orchestrator from the verifier's returned block.
