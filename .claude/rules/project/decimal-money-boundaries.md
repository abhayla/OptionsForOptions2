---
paths:
  - "backend/ofo_app/**"
  - "frontend/**"
  - "tests_app/**"
---
# Scope: path-scoped (backend/ofo_app, frontend, tests_app)

# Money at the app boundaries: Decimal in, Decimal stored, string out

Adapted from `abhayla/algochanakya@bf9faf7:.claude/rules/decimal-not-float-prices.md` (ADR-047). The domain rule is
ADR-008 / ADR-043 ("Money uses Python `Decimal` end to end"); this rule covers the layers the domain does not own.

- Broker or vendor input (float or str): convert at once with `Decimal(str(value))`, never `Decimal(value)` on a float.
- Database: money columns are `NUMERIC` with a fixed scale (prices `NUMERIC(14,2)`); never `Float`/`REAL`/`DOUBLE`;
  defaults are `Decimal("...")` or `server_default`, never a float literal. A JSON payload keeps money as a string or the
  audit log's `{"$decimal": ...}` tag, so hashes re-verify.
- API output: money is serialized as a string (e.g. `"1365.00"`), never as a JSON number; the browser displays it and
  never computes P&L, payoff or Greeks (one engine, ADR-008).
- Float is allowed only inside a math-library call (Black-Scholes, IV) and is converted back at its boundary.
- Why: legacy code converted Decimal to float at the session layer (`algochanakya app/database.py:11-24`) and in API
  schemas; a 0.05 rounding error x 75 quantity is Rs 3.75 per trade.
