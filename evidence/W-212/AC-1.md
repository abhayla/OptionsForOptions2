---
work_item: W-212
requirement: REQ-168
ac: AC-1
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "5cf064384048"
commands: "git rev-parse HEAD (989623c9); python -c over backend/ofo/settings/registry.json (adjustments.* keys); grep -rn 'cost_allow|allowance' backend; read backend/ofo/adjustment/preferences.py"
---
registry.json holds all 15 adjustments.* keys with the spec defaults (delta weekly 0.30 / monthly 0.25, roll points 200/500, iron fly min days 3, reduce divisor 2, near_level 0.5, gap_at_open_until 930, compare range 6, steps 48, moves 1 and 2); preferences.KEYS matches; no per-leg cost allowance exists.

Consumers of compare steps and moves unconfirmed.

Recorded by the orchestrator from the verifier's returned block.
