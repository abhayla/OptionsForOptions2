---
work_item: W-013
ac: AC-4
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "pytest tests/rules/test_model.py tests/engine/test_net_premium.py; stdin net_premium and price_math"
---

AC: AC-4
result: pass
commands: pytest tests/rules/test_model.py tests/engine/test_net_premium.py; stdin net_premium and price_math
observed: ratio 1500 Decimal; golden IC entry 6825.00 = max_profit; FUT 0; AST guard flags sum(l.ltp*l.quantity...) and -l.entry_price
attack: getattr(l,'ltp') passes the guard (gap noted, not an AC failure); no price arithmetic found in rules/

Recorded by the orchestrator from the verifier's returned block.
