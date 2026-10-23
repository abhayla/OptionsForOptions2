---
work_item: W-138
ac: AC-6
requirement: REQ-118
ac_fp: "0d147f0785ab"
result: pass
verified_by: "independent verifiers (Opus, fresh context; round 2 on 962ab74c)"
builder: "builders (Sonnet, builder sequence row 10: build, finish, finish 2, fix 1)"
date: '2026-10-23'
commands: "round 2: pytest tests/broker/test_rate_limit.py; round 1 mutants u9, u10, u11, u14"
---

AC: AC-6
result: pass
commands: round 2: pytest tests/broker/test_rate_limit.py; round 1 mutants u9, u10, u11, u14
observed: rate-limit answers counted per group and user (hashed user ref, never the token) and logged; the third 429 in a minute raises exactly one alert through the Notifier adapter, the fourth none; an alert failure never blocks a read (rate_limit.py:211-247). DEFERRED (#521): the real Notifier sender - in the running app the alert is logged 'alert NOT sent' until an egress door for the Notifier host is reviewed
attack: no dedupe / raw token as user ref / alert error propagating -> killed

Recorded by the orchestrator from the verifier's returned block.
