---
work_item: W-154
requirement: REQ-081
ac: AC-3
result: pass
verified_by: "independent verifier (Opus row 26b check, round 1 at 03bbc1c0 and round 2 at 69eca3d2, PR #576)"
builder: "builders (Sonnet row 26b f17635ab..06c51f6e, fix 624e5400..69eca3d2; orchestrator lint commit 03bbc1c0)"
date: 2026-10-26
ac_fp: "c0c4dee695b9"
commands: "python attack.py; mutation_gate.py"
---
bought NIFTY 22,900 CE LTP 150.00 spot 22,976.85: intrinsic 4995.25, time 4754.75; sold side negative; label 'value of the options, not P&L'; time value from the live price (mutant killed)

Recorded by the orchestrator from the verifier's returned block.
