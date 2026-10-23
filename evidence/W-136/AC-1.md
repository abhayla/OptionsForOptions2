---
work_item: W-136
ac: AC-1
requirement: REQ-050
ac_fp: "1ba55b3de048"
result: fail
verified_by: "independent verifier (Opus, fresh context, round 2 on 5a72453d)"
builder: "builder (Sonnet, builder sequence row 8: build, fix round 1, fix round 2)"
date: '2026-10-22'
commands: "round 2 (Opus) on 5a72453d: pytest tests/marketdata/test_shared_compute*.py tests/marketdata/test_scale_classes.py tests/outcome tests/table (182 passed); mutate.py, 40 key-part mutants in a scratch copy"
---

AC: AC-1
result: fail
commands: round 2 (Opus) on 5a72453d: pytest tests/marketdata/test_shared_compute*.py tests/marketdata/test_scale_classes.py tests/outcome tests/table (182 passed); mutate.py, 40 key-part mutants in a scratch copy
observed: PARKED (#519). Holds in code: IV key service.py:328-338, Greeks key service.py:341-357, forward key snapshot.py:75-87 each hold every input their engine function reads; a second reader of one recorded snapshot computes 0 IV, 0 Greeks, 0 forwards with Decimal-equal figures (test_core_* in tests/marketdata/test_shared_compute.py)
attack: 30 of 40 key-part removals stay green (e.g. Greeks key without leg.iv, forward key without q.bid / q.ask, forward scope without expiry or instant, IV key without the implied yield): a later edit dropping one would serve stale figures with every test green. Killed: iv price, forward spot and quotes, spot ltp (M15), IV instant, feed owner, both figure names

Recorded by the orchestrator from the verifier's returned block.
