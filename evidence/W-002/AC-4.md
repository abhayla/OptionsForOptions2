---
work_item: W-002
ac: AC-4
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/engine/test_decimal_policy.py; attack with Decimal(4.76), '4.765', NaN, sNaN, Infinity, -1, float into every BS money input and estimate_now levels"
---

AC: AC-4
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/engine/test_decimal_policy.py; attack with Decimal(4.76), '4.765', NaN, sNaN, Infinity, -1, float into every BS money input and estimate_now levels
observed: 21 passed; all 49 bad combinations refused; valid Decimal('4.760') accepted; golden -322.50 exact
attack: float-built and sub-paisa values into every BS money input: refused. Gap (test coverage only): no direct forward_price float/NaN test; code refuses both.

Recorded by the orchestrator from the verifier's returned block.
