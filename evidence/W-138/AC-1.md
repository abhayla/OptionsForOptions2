---
work_item: W-138
ac: AC-1
requirement: REQ-118
ac_fp: "adfe70b84857"
result: pass
verified_by: "independent verifiers (Opus, fresh context; round 2 on 962ab74c)"
builder: "builders (Sonnet, builder sequence row 10: build, finish, finish 2, fix 1)"
date: '2026-10-23'
commands: "round 2 (Opus) on 962ab74c: pytest tests/broker/test_rate_limit.py; mutation_gate.py mutants-unit.json; probe_keyless.py through the real urllib door"
---

AC: AC-1
result: pass
commands: round 2 (Opus) on 962ab74c: pytest tests/broker/test_rate_limit.py; mutation_gate.py mutants-unit.json; probe_keyless.py through the real urllib door
observed: limits per group in one place with source and date (rate_limit.py:49 GROUP_RATES; order_limits_registry.py source URL and 2026-10-22/23; F-60); one bucket per group for the whole app, keyed by the app key - a keyless call (instrument download) joins it (rate_limit.py:167-168). MINOR #522: the app key is read from the process environment only, not .env
attack: keyless + keyed calls in one second spaced 0.1 s apart; mutants r2-1, r2-3, r2-4, r2-9 killed

Recorded by the orchestrator from the verifier's returned block.
