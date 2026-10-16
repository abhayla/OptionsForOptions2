---
paths:
  - "backend/ofo_app/**"
---
# Scope: path-scoped (backend/ofo_app)

# FastAPI and SQLAlchemy code (REQ-075, ADR-093)

- Every route declares a `response_model` built on `ApiModel` (a test asserts it); money leaves the API as a string.
- Dependencies use `Annotated[T, Depends(...)]` (ruff FAST002 ratchet); one DB session per request via `get_db`.
- SQL values are always bound parameters; f-strings may only interpolate module constants (table names), marked
  `# noqa: S608 constant table name`.
- Every Kite request goes through a door (`ofo/broker/kite_http.py`, `ofo_app/kite_http.py`); a new Kite call is
  added to `ALLOWED_CALLS` first (REQ-073 AC-4). Hosts, headers and timeouts come from one module, never retyped.
- Reuse the shared Kite helpers (headers, JSON-with-Decimal parse, HTTP error to code) instead of writing a fourth copy.
- Errors returned to users come from the error catalogue (`ofo/errors`), never ad-hoc strings.
- Tests for this layer run as the limited `ofo_app` role; run one test file locally, the full suite in CI.
