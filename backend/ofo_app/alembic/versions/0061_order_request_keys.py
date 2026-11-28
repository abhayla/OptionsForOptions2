"""The durable order request key: public.order_request_keys (Lane FD3 item 2; ADR-017, ADR-330 (58), ADR-048).

Spec basis: ADR-016 to ADR-019 (an unresolved outcome blocks a second placement; no auto retry; the same Confirm sent
twice must not place twice); ADR-330 (58) (paper and real: one rule, the door tag only); ADR-008; ADR-048 (the limited
application role: SELECT, INSERT and UPDATE of state, result and finished_at only, no DELETE).

Why: Lane FD2 kept the key in Redis for 600 s. A Redis flush or restart, or an outcome older than ten minutes, lost it,
and a repeated Confirm then placed again. The record of truth is now this table: the claim is written IN THE SAME
TRANSACTION as the orders (``INSERT ... ON CONFLICT DO NOTHING RETURNING``), so a crash can never store the orders
without the key or the key without the orders. Redis may stay as the fast path.

Changes (owner-run, one transaction; ADDITIVE: ONE new table, nothing existing changed):
- public.order_request_keys(user_ref, request_key uuid, strategy_id -> public.strategies(id), body_sha256, door
  ('paper'|'real'), state ('pending'|'done'), result jsonb, created_at, finished_at); primary key
  (user_ref, request_key). result: paper ``{"cancelled_stops": [...]}``, real ``{"plan_number": n}``.
- Grants to the application role: SELECT; INSERT on every column; UPDATE on state, result, finished_at only. No DELETE.
- downgrade: drops the table.

Old-code compatibility: additive. Old code never reads or writes the table and no existing object is touched, so it
keeps working against the migrated database (it keeps using Redis only). Deploy order: migrate first or last. New code
on an un-migrated database refuses every KEYED order with the catalogue's "could not check" sentence (503, nothing
stored) and still places orders without a key.

Revision ID: 0061_order_request_keys
Revises: 0060_plan_stamp_only_on_switch
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0061_order_request_keys"
down_revision = "0060_plan_stamp_only_on_switch"
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


_BASE = _load("0009_minute_history.py", "ofo_migration_0009_for_0061")._BASE

TABLE = "public.order_request_keys"
INSERT_COLUMNS = ("user_ref", "request_key", "strategy_id", "body_sha256", "door", "state", "result", "created_at",
                  "finished_at")
UPDATE_COLUMNS = ("state", "result", "finished_at")


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(
        f"""
        CREATE TABLE {TABLE} (
            user_ref    TEXT        NOT NULL CHECK (user_ref <> ''),
            request_key UUID        NOT NULL,
            strategy_id BIGINT      NOT NULL REFERENCES public.strategies (id),
            body_sha256 TEXT        NOT NULL CHECK (body_sha256 ~ '^[0-9a-f]{{64}}$'),
            door        TEXT        NOT NULL CHECK (door IN ('paper', 'real')),
            state       TEXT        NOT NULL CHECK (state IN ('pending', 'done')),
            result      JSONB       NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            finished_at TIMESTAMPTZ NULL,
            PRIMARY KEY (user_ref, request_key)
        )
        """
    )
    op.execute(f"REVOKE ALL ON TABLE {TABLE} FROM PUBLIC")
    op.execute(f'REVOKE ALL ON TABLE {TABLE} FROM "{role}"')
    op.execute(f'GRANT SELECT ON TABLE {TABLE} TO "{role}"')
    op.execute(f'GRANT INSERT ({", ".join(INSERT_COLUMNS)}) ON TABLE {TABLE} TO "{role}"')
    op.execute(f'GRANT UPDATE ({", ".join(UPDATE_COLUMNS)}) ON TABLE {TABLE} TO "{role}"')
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    op.execute(f"DROP TABLE {TABLE}")
