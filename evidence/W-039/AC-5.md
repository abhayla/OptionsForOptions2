---
work_item: W-039
ac: AC-5
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/instruments/test_sources.py tests/rules/test_model.py tests/engine/test_black_scholes.py; python -m pytest -q -p no:cacheprovider; python -c probes of validate_source (12 URLs), the money-guard AST checker (11 snippets), forward_price/bs_price (NaN/sNaN/Infinity/float/Decimal(float))"
---

AC: AC-5
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/instruments/test_sources.py tests/rules/test_model.py tests/engine/test_black_scholes.py; python -m pytest -q -p no:cacheprovider; python -c probes of validate_source (12 URLs), the money-guard AST checker (11 snippets), forward_price/bs_price (NaN/sNaN/Infinity/float/Decimal(float))
observed: 50 passed; 1311 passed; https://, https:///x, https://:443/x, https://?a=b, https://user@/x, http://api.kite.trade/instruments refused; https://api.kite.trade/instruments accepted; getattr literal (2/3-arg), attrgetter, operator.attrgetter, dotted attrgetter flagged; getattr(leg,'quantity') not flagged; engine NaN/Infinity/float refused; forward_price(42,0.5,0.10)=44.15 vs 42*e^0.05=44.1534
attack: MINOR: https://%20/x, 'https://exa mple.com' and a NUL host accepted (hostname only checked non-empty; REQ-053 AC-5 asks no more). getattr(leg, name) with a variable not flagged (static limit). Decimal(0.1) as a rate accepted (a ratio, not paise; untested).

Recorded by the orchestrator from the verifier's returned block.
