"""A small per-user setting table: one JSON value per (user, key) (W-124).

Basis: REQ-087 AC-3 ("kept as a per-user preference": the chain's strikes-each-side); ADR-165 (8) (the user comes from
the session, never hard-coded); ADR-048 (the limited application role); ADR-023 (the database clock); ADR-093 (the
migration rules). Written generic so the margin preference (cluster B1) and the strategy preferences (A4) reuse it:
the allowed KEYS and the shape of each VALUE live in ``ofo_app.user_setting_store``, not in the database.

Copy from: none - modelled on 0021's table, guard trigger, grants and allowlist block.

Changes (owner-run, one transaction):
- public.user_settings: PRIMARY KEY (user_ref, key); ``key`` is a closed lower-case dotted word (CHECK); ``value`` JSONB
  (an object, array, string, number or boolean the store validated); ``updated_at`` stamped by the guard trigger from
  the database clock on every write (the application cannot set it).
- Guard trigger (SQLSTATE OF022): a row is never deleted, and an update changes ONLY ``value`` (user_ref and key are
  fixed; updated_at is re-stamped).
- Grants: the application role gets SELECT, INSERT (user_ref, key, value) and UPDATE (value); no DELETE or TRUNCATE.
- public.ofo_assert_app_role_allowlist: the predecessor's chain text (read from down_revision) plus block 19.
- downgrade: refuses while any setting row is stored (a preference is the user's record); otherwise drops what upgrade
  made.

Revision ID: 0022_user_settings
Revises: 0021_strategy_tracking
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0022_user_settings"
down_revision = "0021_strategy_tracking"
branch_labels = None
depends_on = None


def _load(filename: str, name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load the migration {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: The predecessor publishes the allow-list chain text and its helpers (read from down_revision, never named here).
_PREVIOUS = _load(f"{down_revision}.py", "ofo_migration_predecessor_for_0022")
_M16 = _PREVIOUS._M16  # 0016: the table block helper
_BASE = _PREVIOUS._BASE  # 0001
_M4 = _PREVIOUS._M4  # 0004: _md5_body

SEARCH_PATH = _M16.SEARCH_PATH
SQLSTATE = "OF022"
SETTINGS = "public.user_settings"
GUARD = "public.user_settings_guard"
TRIGGER = "user_settings_guard"
INSERT_COLUMNS = ("user_ref", "key", "value")
UPDATE_COLUMNS = ("value",)
ALLOWLIST_BLOCK_MARKER = "-- 19. user settings"


def _guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'user settings are never deleted' USING ERRCODE = '{SQLSTATE}';
            END IF;
            IF TG_OP = 'UPDATE' AND (NEW.user_ref IS DISTINCT FROM OLD.user_ref
                                     OR NEW.key IS DISTINCT FROM OLD.key) THEN
                RAISE EXCEPTION 'a user setting changes only its value' USING ERRCODE = '{SQLSTATE}';
            END IF;
            NEW.updated_at := clock_timestamp();
            RETURN NEW;
        END
        $fn$
        """


PIN = _M4._md5_body(_guard_sql())


def _block() -> str:
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (W-124): user_settings: SELECT, INSERT (user_ref, key, value) and UPDATE (value) exactly
    --    as granted, no DELETE / TRUNCATE; the guard trigger enabled with its pinned body
    IF phase = 'post' THEN
{_M16._table_block(SETTINGS, "user_settings", INSERT_COLUMNS, UPDATE_COLUMNS, GUARD, TRIGGER, PIN)}
    END IF;
"""


def previous_allowlist_sql() -> str:
    return _PREVIOUS.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """The predecessor's chain text plus block 19. Fails closed (RuntimeError) on a changed shape or a block 19 already
    in."""
    previous = previous_allowlist_sql()
    insert_before = _M16._INSERT_BEFORE
    if previous.count(insert_before) != 1 or ALLOWLIST_BLOCK_MARKER in previous:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the user settings checks safely")
    return previous.replace(insert_before, _block() + insert_before, 1)


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(
        f"""
        CREATE TABLE {SETTINGS} (
            user_ref   TEXT        NOT NULL CHECK (user_ref <> ''),
            key        TEXT        NOT NULL CHECK (key ~ '^[a-z][a-z0-9_.]{{0,63}}$'),
            value      JSONB       NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (user_ref, key)
        )
        """
    )
    op.execute(_guard_sql())
    op.execute(f"CREATE TRIGGER {TRIGGER} BEFORE INSERT OR UPDATE OR DELETE ON {SETTINGS} "
               f"FOR EACH ROW EXECUTE FUNCTION {GUARD}()")
    op.execute(f"REVOKE ALL ON FUNCTION {GUARD}() FROM PUBLIC")
    op.execute(f'REVOKE ALL ON FUNCTION {GUARD}() FROM "{role}"')
    op.execute(f"REVOKE ALL ON TABLE {SETTINGS} FROM PUBLIC")
    op.execute(f'REVOKE ALL ON TABLE {SETTINGS} FROM "{role}"')
    op.execute(f'GRANT SELECT ON TABLE {SETTINGS} TO "{role}"')
    op.execute(f'GRANT INSERT ({", ".join(INSERT_COLUMNS)}) ON TABLE {SETTINGS} TO "{role}"')
    op.execute(f'GRANT UPDATE ({", ".join(UPDATE_COLUMNS)}) ON TABLE {SETTINGS} TO "{role}"')
    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def refuse_downgrade_sql() -> str:
    """A stored preference is the user's record: the downgrade refuses (an exception) while any row exists."""
    return f"""
        DO $$
        BEGIN
            EXECUTE 'LOCK TABLE {SETTINGS} IN ACCESS EXCLUSIVE MODE';
            IF EXISTS (SELECT 1 FROM {SETTINGS}) THEN
                RAISE EXCEPTION 'refusing downgrade: {SETTINGS} holds user settings';
            END IF;
        END
        $$
        """  # noqa: S608 constant table name


def downgrade() -> None:
    op.execute(refuse_downgrade_sql())
    role = _BASE._app_role()
    op.execute(previous_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {_BASE.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"DROP TABLE {SETTINGS}")
    op.execute(f"DROP FUNCTION {GUARD}()")
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
