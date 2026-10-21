---
paths:
  - "backend/ofo_app/alembic/**"
---
# Scope: path-scoped (Alembic migrations)

# Migrations (REQ-075, ADR-093)

- One change per revision; never edit a revision that has merged to main - add a new one.
- Every revision has a real `downgrade`, or a `downgrade` that raises with the reason it cannot be undone.
- Money columns are `NUMERIC` with a fixed scale (prices `NUMERIC(14,2)`); never Float/REAL/DOUBLE. One exception
  (ADR-126): a price copied from Zerodha that is not a traded price, e.g. an adopted leg's average, is unscaled
  `NUMERIC` with a > 0 and finite CHECK, so no real average (7.016666666666667) is rounded.
- No empty migrations (`python scripts/alembic_migration_guard.py`).
- Migrations run as the owner role; grants for the limited `ofo_app` role are part of the same revision.
- Only one open branch adds a migration at a time (the migration lane); check `alembic heads` is single before merging.
