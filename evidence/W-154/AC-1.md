---
work_item: W-154
requirement: REQ-081
ac: AC-1
result: pass
verified_by: "independent verifier (Opus row 26b check, round 1 at 03bbc1c0 and round 2 at 69eca3d2, PR #576)"
builder: "builders (Sonnet row 26b f17635ab..06c51f6e, fix 624e5400..69eca3d2; orchestrator lint commit 03bbc1c0)"
date: 2026-10-26
ac_fp: "0d3b89f27949"
commands: "python attack.py; npx vitest run tests/money-summary.test.js"
---
net premium Get 4364.75 per unit 67.15 on the 2026-10-15 condor; a futures leg -> amount absent with 'premium and futures value cannot be added'
screen shows the server text verbatim ('Get ₹4,754.75' on the replay condor)

Recorded by the orchestrator from the verifier's returned block.
