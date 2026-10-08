---
name: options-math-review
description: Review checklist for changes to the calculation engine - Black-Scholes pricing, implied volatility, Greeks, payoff, scenario and P&L formulas. Use when reviewing or briefing work that touches backend/ofo/engine/, backend/ofo/scenario/ or any code producing a P&L, payoff, IV or Greek number.
---

# Options math review

Adapted from `abhayla/algochanakya@bf9faf7:.claude/agents/options-greeks-reviewer.md` (ADR-047). Its numeric
defaults (7% rate, 252 trading days) are NOT this project's: the values below come from the spec.

## Spec values (check every change against these, not against memory)
- Model: European Black-Scholes-Merton with each expiry's implied dividend yield q from put-call parity (ADR-061,
  ADR-063: the engine owns q and every Greek, theta included; callers never rescale an engine output; payoff and the
  CURRENT column stay on spot), time = calendar days / 365 to expiry at 15:30 IST, continuous rate as an
  explicit input, each leg at its own IV implied from its LTP (`spec/business-rules/scenario-calculations.md` §4, ADR-008).
- Rate: an admin setting, default 6.5% p.a. (Q248, `spec/open-questions.md`). Never hardcoded in the engine.
- Formulas in `scenario-calculations.md` are locked; one engine owns every P&L/payoff/Greek number (ADR-008).
- Money: `Decimal`, whole paise for prices (`backend/ofo/engine/legs.py` `require_price`); float only inside the math
  library call, converted back with `Decimal(str(x))` at the boundary.
- Expected move: spot x ATM IV x sqrt(days/365) (Q253).

## Checklist (report PASS / WARN / FAIL per line, with file:line)
- Black-Scholes d1/d2 and call/put prices match the standard definition; put-call parity holds on a sample.
- IV solver: bounded iterations, a defined result for zero premium (no NaN), deep ITM/OTM handled, no negative sqrt.
- Zero time to expiry (T = 0, expiry-day 15:30): no division by zero in sqrt(T); intrinsic value used.
- Greeks: signs and magnitudes sane on the golden Iron Condor (`tests/engine/test_golden_iron_condor.py`).
- No second calculator: grep the diff for payoff/P&L/Greek math outside `backend/ofo/engine/`.
- No float money: grep the diff for `float(` and float literals on prices, premiums, P&L.
- Expected values in tests come from the spec or an independent computation, never from running the code under test
  (finding `test-asserts-implementation-output`).
