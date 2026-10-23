---
work_item: W-129
ac: AC-2
requirement: REQ-001
ac_fp: "e7e7e95e6899"
result: pass
verified_by: "independent verifier (Sonnet, fresh context, round 2 on 3162e50f)"
builder: "builder (Sonnet, builder sequence row 1)"
date: '2026-10-22'
commands: "read backend/ofo/engine/legs.py; pytest tests_app/test_underlying_refusal.py::test_an_index_row_as_a_leg_with_a_provider_is_refused_with_a_catalogue_message tests_app/test_index_leg_save.py; round 1: POST /strategies with INDEX row 3278958 (rolled back)"
---

AC: AC-2
result: pass
commands: read backend/ofo/engine/legs.py; pytest tests_app/test_underlying_refusal.py::test_an_index_row_as_a_leg_with_a_provider_is_refused_with_a_catalogue_message tests_app/test_index_leg_save.py; round 1: POST /strategies with INDEX row 3278958 (rolled back)
observed: Instrument CE/PE/FUT x Action BUY/SELL = six types; INDEX row as a leg: outcome 200 REFUSED 'unknown instrument' (snapshot.py), save 422 STRATEGY_VALIDATION_401 (strategy_store.py:123), never 500
attack: INDEX id on save over HTTP (round 1) and on outcome with the provider; weak spot (MINOR, deferred issue): test_index_leg_save.py can skip and has a vacuous assert

Recorded by the orchestrator from the verifier's returned block.
