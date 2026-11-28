"""The order attempt record: public.order_attempts (Lane B2, weekend round 3; ADR-016 to ADR-019, ADR-330 (58)).

Spec basis: ADR-016 to ADR-019 (submitted is not executed; no automatic retry; an unresolved outcome blocks the next
execution), ADR-330 (58) (paper and real alike), ADR-048 (the limited application role, no DELETE).

Why: the request key (0061) de-duplicates only the SAME key and body. A second request with another body or another key
(a changed ``prices_not_live_confirmed``, an add whose key follows the live price) was a new request, so a second order
could follow an order whose outcome was never known (crash between store and reply, a failed or late commit). The
server must be the guarantee: while a strategy has an order attempt whose outcome is not known, every further order
request for it is refused, whatever its key or body.

Changes (owner-run, one transaction; ADDITIVE: ONE new table, nothing existing changed):
- public.order_attempts(id, user_ref, strategy_id -> public.strategies(id), door ('paper'|'real'), started_at, state
  ('open'|'stored'|'not_stored'), resolved_at). A partial unique index allows ONE 'open' attempt per strategy: opening
  is the atomic claim, so two tabs cannot both pass.
- Grants to the application role: SELECT; INSERT on user_ref, strategy_id, door and state only (the
  database sets started_at; a request cannot back-date or pre-close an attempt); UPDATE on state and resolved_at
  only; no DELETE.
- downgrade: drops the table.

Old-code compatibility: additive; old code never reads or writes the table and keeps working. New code on an
un-migrated database refuses every order request (fail closed) until the migration runs.

Revision ID: 0063_order_attempts
Revises: 0062_order_request_keys_expiry
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0063_order_attempts"
down_revision = "0062_order_request_keys_expiry"
branch_labels = None
depends_on = None


def _load(filename: str, name: str):
    path = Path(__file__).with_name(filename)
    found = importlib.util.spec_from_file_location(name, path)
    if found is None or found.loader is None:
        raise RuntimeError(f"cannot load the migration {path}")
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)
    return module


_BASE = _load("0009_minute_history.py", "ofo_migration_0009_for_0063")._BASE

TABLE = "public.order_attempts"
INSERT_COLUMNS = ("user_ref", "strategy_id", "door", "state")
UPDATE_COLUMNS = ("state", "resolved_at")


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(
        f"""
        CREATE TABLE {TABLE} (
            id          BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_ref    TEXT        NOT NULL CHECK (user_ref <> ''),
            strategy_id BIGINT      NOT NULL REFERENCES public.strategies (id),
            door        TEXT        NOT NULL CHECK (door IN ('paper', 'real')),
            started_at  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            state       TEXT        NOT NULL CHECK (state IN ('open', 'stored', 'not_stored')),
            resolved_at TIMESTAMPTZ NULL,
            CHECK ((state = 'open') = (resolved_at IS NULL))
        )
        """
    )
    op.execute(f"CREATE UNIQUE INDEX order_attempts_one_open ON {TABLE} (strategy_id) WHERE state = 'open'")
    op.execute(f"CREATE INDEX order_attempts_strategy ON {TABLE} (strategy_id, started_at)")
    op.execute(f"REVOKE ALL ON TABLE {TABLE} FROM PUBLIC")
    op.execute(f'REVOKE ALL ON TABLE {TABLE} FROM "{role}"')
    op.execute(f'GRANT SELECT ON TABLE {TABLE} TO "{role}"')
    op.execute(f'GRANT INSERT ({", ".join(INSERT_COLUMNS)}) ON TABLE {TABLE} TO "{role}"')
    op.execute(f'GRANT UPDATE ({", ".join(UPDATE_COLUMNS)}) ON TABLE {TABLE} TO "{role}"')
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    op.execute(f"DROP TABLE {TABLE}")
