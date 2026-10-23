---
work_item: W-143
ac: AC-3
requirement: REQ-028
ac_fp: "6f59c0344249"
result: pass
verified_by: "independent verifiers (Opus, fresh context, start check on 0e574b58; Sonnet, fresh context, AC-2 on 025a22cf)"
builder: "builders (earlier work items; builder sequence row 15 start check, no new code)"
date: '2026-10-23'
commands: "start check (Opus, fresh) on 0e574b58; mutant M8 killed"
---

AC: AC-3
result: pass
commands: start check (Opus, fresh) on 0e574b58; mutant M8 killed
observed: a new template added as data only matches (22 templates load; 25050/25200/25350 -> 'Call Ladder Scratch' k=1 w=3); a duplicate shape is refused at load
attack: scratch catalogue with a new template; loader overlap mutant M8

Recorded by the orchestrator from the verifier's returned block.
