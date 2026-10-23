---
work_item: W-138
ac: AC-4
requirement: REQ-118
ac_fp: "cf5faa878bc0"
result: pass
verified_by: "independent verifiers (Opus, fresh context; round 2 on 962ab74c)"
builder: "builders (Sonnet, builder sequence row 10: build, finish, finish 2, fix 1)"
date: '2026-10-23'
commands: "round 2: mutants r2-6b, r2-7b, r2-8, r2-10; test_two_429s_on_the_margin_read_block_the_margin_gate_never_a_figure"
---

AC: AC-4
result: pass
commands: round 2: mutants r2-6b, r2-7b, r2-8, r2-10; test_two_429s_on_the_margin_read_block_the_margin_gate_never_a_figure
observed: a 429 starts the group's 10 s cooldown (F-60) and nothing is sent into it (rate_limit.py:206-210); a read retries at most twice, then busy; the margin gate then blocks with no figure (ADR-094)
attack: cooldown dropped or extended, re-check removed, 3 retries -> killed

Recorded by the orchestrator from the verifier's returned block.
