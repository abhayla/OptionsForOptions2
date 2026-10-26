---
work_item: W-154
requirement: REQ-081
ac: AC-8
result: pass
verified_by: "independent verifier (Opus row 26b check, round 1 at 03bbc1c0 and round 2 at 69eca3d2, PR #576)"
builder: "builders (Sonnet row 26b f17635ab..06c51f6e, fix 624e5400..69eca3d2; orchestrator lint commit 03bbc1c0)"
date: 2026-10-26
ac_fp: "0afcf58e6212"
commands: "python attack.py; mutation_gate.py"
---
one priced + one unpriced leg -> figures absent with a reason, never a partial sum (mutant M2 killed by the unit tests)
