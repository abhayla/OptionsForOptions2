---
paths:
  - "backend/ofo/**"
  - "scripts/**"
---
# Scope: path-scoped (backend/ofo, scripts)

# Python domain code (REQ-075, ADR-093)

- Standard library only in `backend/ofo/` (ADR-043); third-party code lives in `backend/ofo_app/`.
- Money is `Decimal` end to end (ADR-008); JSON is parsed with `parse_float=Decimal`, or the line says
  `# float-ok: <why this payload holds no money>` (REQ-075 AC-2). `float()` only inside `engine/black_scholes.py`.
- One home per real-world value (REQ-075 AC-1): IST and market/settlement times in `ofo/timeutil.py`, paise in
  `ofo/money.py`, segment/broker/index names in `ofo/instruments/models.py`. Import them; never retype them.
- Datetimes are timezone-aware (IST from `ofo/timeutil.py`); never `datetime.now()` / `date.today()` in the domain:
  the caller passes the date in (no wall clock in tests either).
- Before writing a helper, grep for an existing one (lot alignment, buy/sell checks, tick rounding); call it, don't copy it.
- No `except Exception` in execution/, orders/, reconciliation/ unless it re-raises or records a blocking state
  (ruff BLE001 ratchet).
- Fail closed: an unknown state, shape or answer blocks or warns; it never silently passes.
- After editing, the edit hook prints ruff findings for that file; fix them before moving on.
