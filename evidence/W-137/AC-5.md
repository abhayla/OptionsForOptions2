---
work_item: W-137
ac: AC-5
requirement: REQ-113
ac_fp: "58dadaf62eb6"
result: pass
verified_by: "independent verifiers (Opus, fresh context; final round on 4b829faf)"
builder: "builders (Sonnet, builder sequence row 9: parts A0, A1, B, C and their fix/finish rounds)"
date: '2026-10-23'
commands: "final round: mutant M13; DB run (test_feed_user_isolation.py)"
---

AC: AC-5
result: pass
commands: final round: mutant M13; DB run (test_feed_user_isolation.py)
observed: price part at the bus: per-user streams and keys, and decode_message refuses another user's message (feed_bus.py:137); market-wide figures still once per snapshot (REQ-050). Deferred: the order-event part (order path) and a two-user BROWSER test - the API serves one user today (OWNER_REF, ADR-060), so no second user's browser exists to test
attack: user check removed -> killed by test_another_users_message_in_this_users_stream_is_refused

Recorded by the orchestrator from the verifier's returned block.
