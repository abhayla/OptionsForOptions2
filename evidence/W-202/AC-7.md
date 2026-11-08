---
work_item: W-202
requirement: REQ-155
ac: AC-7
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "88e6a488fc9c"
commands: "read tests_app/test_adjustment_approaches_route.py:85-118,326-335; read backend/ofo_app/routes/adjustment.py:468-498,517-521; PYTHONPATH=backend python -c len(APPROACH_IDS)"
---
test_adjustment_approaches_route.py:335 asserts engine_seconds <= 1; the timer (adjustment.py:476-498) covers guards read, price_all, second pass and more_reader; APPROACH_IDS has 15 ids, so the bound is stricter than the AC's 7. Attack: engine time includes more_reader, which can wait in production; in the test the readers are stubbed, so that wait is not exercised.

The 1 s figure is stub-timed, not a live measurement. DB proof owed: tests_app/test_adjustment_approaches_route.py::test_ac7_seven_approaches_engine_time_at_most_one_second_and_no_order_path.

Recorded by the orchestrator from the verifier's returned block.
