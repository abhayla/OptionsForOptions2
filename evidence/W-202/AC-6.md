---
work_item: W-202
requirement: REQ-155
ac: AC-6
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "842cf9d0fce5"
commands: "read backend/ofo_app/routes/adjustment.py:286-305; read backend/ofo_app/outcome_margin.py:161-227; PYTHONPATH=backend python -c margin_block(MARGIN / margin_unreadable() / margin_empty() / None); read tests_app/test_outcome_margin.py:176,277,310,316-319, tests_app/test_adjustment_approaches_route.py:214-263"
---
margin_block called directly: not signed in -> not_available_yet, value None, 'Margin not available: ... needs your Zerodha login'; timeout -> unreadable 'could not be read just now', value None; empty -> empty, value None; None -> failed; stated figures carry at=checked_at; a figure is never 0. Attack: a timeout in outcome_margin._fetch (except Exception) returns margin_unreadable(), tested at test_outcome_margin.py:316.

Reason is catalogue text, not Zerodha's raw message. Not-signed-in covered by margin_answer unit tests + the direct call, not by an adjustment-route test.

Recorded by the orchestrator from the verifier's returned block.
