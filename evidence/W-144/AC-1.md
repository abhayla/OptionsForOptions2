---
work_item: W-144
ac: AC-1
requirement: REQ-038
ac_fp: "5080421a029a"
result: pass
verified_by: "independent verifiers (Opus, fresh context; round 1 on d99b2097, round 2 on 735ba1a6; DB part CI #525 on f5a1059c)"
builder: "builders (Opus, builder sequence row 16: build, fix 1)"
date: '2026-10-23'
commands: "round 1 (Opus, fresh) on d99b2097: pytest tests/strategy tests/reconciliation (690 passed); start check on 0e574b58 mutant M6 killed"
---

AC: AC-1
result: pass
commands: round 1 (Opus, fresh) on d99b2097: pytest tests/strategy tests/reconciliation (690 passed); start check on 0e574b58 mutant M6 killed
observed: definition and live-state field sets do not overlap; 'ltp' on a leg -> unknown_key; the version row keeps the definition JSONB in its own column and the broker actual in a separate outcome column (0022_strategy_versions.py)
attack: looked for live-state fields leaking into VersionOut or the version definition: none

Recorded by the orchestrator from the verifier's returned block.
