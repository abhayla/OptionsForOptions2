---
work_item: W-087
ac: AC-2
requirement: REQ-001
ac_fp: "e7e7e95e6899"
result: pass
verified_by: "verifier (sonnet/high, fresh context, docs/gc-1-closeout b643356)"
builder: "none (verify-only card; code on main)"
date: '2026-10-16'
commands: "python -m pytest -q -p no:cacheprovider tests/strategy/test_strategy_model.py::test_strategy_holds_all_six_leg_types_across_two_expiries; python tools/ac_fp.py REQ-001 AC-2 --yaml; python -c (ofo.engine.legs Leg/Action/Instrument probes)"
---

AC: AC-2
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/strategy/test_strategy_model.py::test_strategy_holds_all_six_leg_types_across_two_expiries; python tools/ac_fp.py REQ-001 AC-2 --yaml; python -c (ofo.engine.legs Leg/Action/Instrument probes)
observed: passed within the 175; Action=[BUY,SELL], Instrument=[CE,PE,FUT], so exactly 2x3=6 combinations; the test builds all six and asserts len==6 and net-zero expiry P&L
attack: Leg with action='BUY' string, instrument='XX', CE with strike None, FUT with a strike, float strike, float entry_price: all refused with ValueError (e.g. 'a futures leg has no strike', 'strike must be a decimal.Decimal, got float'). The test only proves the six are held; closure comes from the two enums and the Leg constructor, which I probed directly.

Recorded by the orchestrator from the verifier's returned block.
