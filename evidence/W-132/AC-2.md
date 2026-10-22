---
work_item: W-132
ac: AC-2
requirement: REQ-117
ac_fp: "5c70f063bd79"
result: pass
verified_by: "independent verifier (Opus, fresh context, round 2 on 23eee95b)"
builder: "builder (Sonnet, builder sequence row 4: build, finish, fix round 1)"
date: '2026-10-22'
commands: "round 2: grep of every cited source; tests/broker/test_broker_flags.py (a test reads each cited file for the call it claims)"
---

AC: AC-2
result: pass
commands: round 2: grep of every cited source; tests/broker/test_broker_flags.py (a test reads each cited file for the call it claims)
observed: every Zerodha flag carries a source and the date 2026-10-22: funds_read -> kite_margin.py FUNDS_PATH /user/margins (fixed in round 1), positions_read -> kite_reads.py, basket_margin_quote -> kite_margin.py, intraday_product -> the real profile reply (MIS listed), basket and order-update stream -> Kite docs URLs; broker_held_triggers OFF until REQ-100 AC-1's core proof
attack: round 1 found funds_read citing the wrong file (fixed 23eee95b); the Kite docs anchors were not fetched (no Kite calls in verification)

Recorded by the orchestrator from the verifier's returned block.
