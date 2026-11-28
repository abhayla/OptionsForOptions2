"""The order request key table: a narrower INSERT grant and a bounded expiry (Lane RA N8; ADR-017, ADR-048).

Spec basis: ADR-016 to ADR-019 (the same Confirm sent twice must not place twice), ADR-048 (the limited application
role: the least privilege that works), ADR-330 (58). Review N8 of round 2 (Lane Z2).

Why: migration 0061 granted INSERT on nine columns where the code writes six (``result``, ``created_at`` and
``finished_at`` are never in the INSERT: the first has no value yet, the others come from defaults and the UPDATE), and
it granted no DELETE and had no expiry: one row per keyed order, forever.

Changes (owner-run, one transaction; the table and its rows are not touched):
- INSERT on public.order_request_keys narrows to the six columns ``request_key.py`` writes: user_ref, request_key,
  strategy_id, body_sha256, door, state.
- public.expire_order_request_keys(): a SECURITY DEFINER function (search_path pinned) that deletes the rows older than
  the replay window, 7 days (``request_key.REPLAY_WINDOW_DAYS``; the Redis fast path keeps a key 10 minutes, the
  unknown-outcome window is 2 minutes, a Confirm repeated a week later is a new decision). It takes no argument, so the
  application role cannot widen the window, and the role gets EXECUTE on it only: still NO DELETE on the table, so a
  fresh key (the guard against a double order) can never be removed by the application role.
- downgrade: drops the function and puts the nine-column INSERT back.

Old-code compatibility: additive and narrowing. Old code writes the same six columns, so it keeps working; it never
calls the function. Deploy order: migrate first or last (new code on an un-migrated database skips the expiry, its
failure is swallowed in a savepoint).

Revision ID: 0062_order_request_keys_expiry
Revises: 0061_order_request_keys
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0062_order_request_keys_expiry"
down_revision = "0061_order_request_keys"
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


_BASE = _load("0009_minute_history.py", "ofo_migration_0009_for_0062")._BASE

TABLE = "public.order_request_keys"
FUNCTION = "public.expire_order_request_keys"
WRITTEN_COLUMNS = ("user_ref", "request_key", "strategy_id", "body_sha256", "door", "state")
OLD_INSERT_COLUMNS = ("user_ref", "request_key", "strategy_id", "body_sha256", "door", "state", "result", "created_at",
                      "finished_at")
REPLAY_WINDOW_DAYS = 7  # the literal in the function body = request_key.REPLAY_WINDOW_DAYS (a test pins both)


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(f'REVOKE INSERT ON TABLE {TABLE} FROM "{role}"')  # table level; it also removes the column grants
    op.execute(f'GRANT INSERT ({", ".join(WRITTEN_COLUMNS)}) ON TABLE {TABLE} TO "{role}"')
    op.execute(  # a plain literal: the window and the table are fixed text, nothing is interpolated
        """
        CREATE FUNCTION public.expire_order_request_keys() RETURNS bigint
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $fn$
        DECLARE
            removed bigint;
        BEGIN
            DELETE FROM public.order_request_keys WHERE created_at < clock_timestamp() - INTERVAL '7 days';
            GET DIAGNOSTICS removed = ROW_COUNT;
            RETURN removed;
        END
        $fn$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {FUNCTION}() FROM PUBLIC")
    op.execute(f'GRANT EXECUTE ON FUNCTION {FUNCTION}() TO "{role}"')
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    role = _BASE._app_role()
    op.execute(f"DROP FUNCTION {FUNCTION}()")
    op.execute(f'REVOKE INSERT ON TABLE {TABLE} FROM "{role}"')
    op.execute(f'GRANT INSERT ({", ".join(OLD_INSERT_COLUMNS)}) ON TABLE {TABLE} TO "{role}"')
