---
work_item: W-202
requirement: REQ-155
ac: AC-5
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "c07c8e663127"
commands: "python -m pytest -q -p no:cacheprovider tests/marketdata/test_spot_source.py; read backend/ofo/marketdata/spot_source.py; read kite_http.py:36-56; read adjustment.py:308-324 and 469-470"
---
resolve_spot tries feed, REST, last close, each labelled with source and time; a stale feed, a future tick, a non-finite value and a 200 with no price are refused with a reason. kite_http.py:40-48 allow-lists the index symbols. With no usable source the route returns before=None and a 'Spot not available' text naming each source's reason. Attack: zero/NaN prices and a skewed future time are refused (tests 142-201).

Route-level reply covered only by tests_app/test_adjustment_approaches_route.py (not read).

Recorded by the orchestrator from the verifier's returned block.
