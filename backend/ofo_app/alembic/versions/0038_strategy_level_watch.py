"""A user's watched index level per strategy and direction, as dated append-only rows (GC-IC1 step 4c, approach
A-37; ADR-242).

Spec basis: ADR-242 (A-37 is an adjustment alert: stored per strategy, one active watch per direction, set / cleared
by its owner, evaluated as a yes/no rule through the alert gate); REQ-170 AC-5 (risk exits never read this table);
REQ-168 AC-3 "every read and write is keyed by the user"; ADR-048 (the limited application role); ADR-023 (database
clock).

Copy from: 0037_strategy_monitor_pause.py (append-only guard, statement-level truncate trigger, grants, allow-list
block), the same per-user, per-strategy key plus the direction.

Changes (owner-run, one transaction):
- public.strategy_level_watch: user_ref (non-empty, at most 200), strategy_id (a stored strategy), direction
  ('above' / 'below'), level NUMERIC NULL (NULL = the watch was cleared; otherwise > 0), effective_from TIMESTAMPTZ,
  created_at DEFAULT clock_timestamp(). PRIMARY KEY (user_ref, strategy_id, direction, effective_from). The watch in
  force per direction is the newest row of that direction.
- Append-only guard (BEFORE INSERT OR UPDATE OR DELETE, SQLSTATE OF038, search_path pinned, md5-pinned in the
  allow-list): every UPDATE and DELETE is refused; an INSERT more than 5 seconds in the past is refused; the same
  function on a statement-level BEFORE TRUNCATE trigger refuses TRUNCATE.
- Grants: the application role gets SELECT and column INSERT on user_ref, strategy_id, direction, level,
  effective_from.
- public.ofo_assert_app_role_allowlist: 0037's chain text plus block 30.
- downgrade: refuses (OF038) while any row exists.

Known bypasses (out of the threat model): the table owner or a superuser can drop or disable the guard, then edit rows.

Revision ID: 0038_strategy_level_watch
Revises: 0037_strategy_monitor_pause
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0038_strategy_level_watch"
down_revision = "0037_strategy_monitor_pause"
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


_M37 = _load("0037_strategy_monitor_pause.py", "ofo_migration_0037_for_0038")
_M36 = _M37._M36
_M35 = _M36._M35
_M33 = _M35._M33
_M16 = _M35._M16
_M4 = _M35._M4
_BASE = _M35._BASE
_INSERT_BEFORE = _M35._INSERT_BEFORE

SEARCH_PATH = _M16.SEARCH_PATH
SQLSTATE = "OF038"  # an update, a delete, a truncate or a back-dated insert of a stored level watch
BACKDATE_GRACE_SECONDS = _M33.BACKDATE_GRACE_SECONDS

TABLE = "public.strategy_level_watch"
GUARD = "public.strategy_level_watch_guard"
TRIGGER = "strategy_level_watch_guard"
TRUNCATE_TRIGGER = "strategy_level_watch_no_truncate"
LABEL = "strategy_level_watch"
USER_MAX = _M33.USER_MAX
INSERT_COLUMNS = ("user_ref", "strategy_id", "direction", "level", "effective_from")
NO_UPDATE: tuple[str, ...] = ()
ALLOWLIST_BLOCK_MARKER = "-- 30. strategy level watch"


def _guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'level watches are insert-only: a change or a clear is a new row'
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
            IF NEW.effective_from < clock_timestamp() - interval '{BACKDATE_GRACE_SECONDS} seconds' THEN
                RAISE EXCEPTION 'a level watch takes effect now: a back-dated row is refused'
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
            RETURN NEW;
        END
        $fn$
        """


PIN = _M4._md5_body(_guard_sql())
BEFORE_STATEMENT_TRUNCATE = _M35.BEFORE_STATEMENT_TRUNCATE


def _trigger_checks() -> str:
    """0008's shared check with this table's truncate trigger allowed and checked in its own right (as 0033)."""
    shared = _M16._M8._trigger_check(TABLE, TRIGGER, GUARD, PIN)
    plain = f"AND tgname <> '{TRIGGER}')"
    if shared.count(plain) != 1:
        raise RuntimeError("the shared trigger check changed shape: cannot allow the truncate trigger safely")
    shared = shared.replace(plain, f"AND tgname NOT IN ('{TRIGGER}', '{TRUNCATE_TRIGGER}'))")
    row = f"FROM pg_trigger WHERE tgrelid = '{TABLE}'::regclass AND tgname = '{TRUNCATE_TRIGGER}'"
    return shared + f"""
            IF NOT EXISTS (SELECT 1 {row} AND tgenabled = 'O') THEN
                problems := problems || 'trigger {TRUNCATE_TRIGGER} is missing or not enabled'::TEXT;
            ELSIF (SELECT tgfoid {row}) IS DISTINCT FROM to_regprocedure('{GUARD}()')
                  OR (SELECT tgtype::int {row}) IS DISTINCT FROM {BEFORE_STATEMENT_TRUNCATE}
                  OR (SELECT tgqual IS NOT NULL OR tgattr::text <> '' OR tgnargs <> 0 {row}) THEN
                problems := problems || 'trigger {TRUNCATE_TRIGGER} is not a plain BEFORE TRUNCATE trigger'::TEXT;
            END IF;"""  # noqa: S608 - constant names only


def _block() -> str:
    """Runs inside public.ofo_assert_app_role_allowlist (`r` the role row, `problems` the refusals, `col` TEXT)."""
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (GC-IC1 A-37): SELECT + column INSERT on {", ".join(INSERT_COLUMNS)} only;
    --    no UPDATE / DELETE / TRUNCATE; the guard trigger enabled with its pinned body, no EXECUTE on it
    IF phase = 'post' THEN
        IF to_regclass('{TABLE}') IS NULL THEN
            problems := problems || 'table {TABLE} is missing'::TEXT;
        ELSE
            IF (SELECT relowner FROM pg_class WHERE oid = '{TABLE}'::regclass)
               IS DISTINCT FROM (SELECT relowner FROM pg_class WHERE oid = '{_M16._M3.TABLE}'::regclass) THEN
                problems := problems || 'table {TABLE} is not owned by the catalogue table owner'::TEXT;
            END IF;
{_M16._PREV._privilege_checks(TABLE, LABEL, {"SELECT"})}
{_M16._M3._columns_exactly(TABLE, LABEL, "INSERT", INSERT_COLUMNS)}
{_M16._M3._columns_exactly(TABLE, LABEL, "UPDATE", NO_UPDATE)}
{_M16._M3._guard_function_checks(GUARD, security_definer=False)}
{_trigger_checks()}
        END IF;
    END IF;
"""  # noqa: S608 - constant table and function names only


def previous_allowlist_sql() -> str:
    return _M37.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """0037's chain text plus block 30. Fails closed (RuntimeError) on a changed shape or a block 30 already in."""
    previous = previous_allowlist_sql()
    if previous.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous or "-- 30." in previous:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the level-watch checks safely")
    return previous.replace(_INSERT_BEFORE, _block() + _INSERT_BEFORE, 1)


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(
        f"""
        CREATE TABLE {TABLE} (
            user_ref       TEXT        NOT NULL CHECK (btrim(user_ref) <> '' AND length(user_ref) <= {USER_MAX}),
            strategy_id    BIGINT      NOT NULL REFERENCES public.strategies (id),
            direction      TEXT        NOT NULL CHECK (direction IN ('above', 'below')),
            level          NUMERIC     NULL CHECK (level IS NULL OR level > 0),
            effective_from TIMESTAMPTZ NOT NULL,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (user_ref, strategy_id, direction, effective_from)
        )
        """
    )
    op.execute(_guard_sql())
    op.execute(f"CREATE TRIGGER {TRIGGER} BEFORE INSERT OR UPDATE OR DELETE ON {TABLE} "
               f"FOR EACH ROW EXECUTE FUNCTION {GUARD}()")
    op.execute(f"CREATE TRIGGER {TRUNCATE_TRIGGER} BEFORE TRUNCATE ON {TABLE} FOR EACH STATEMENT "
               f"EXECUTE FUNCTION {GUARD}()")
    op.execute(f"REVOKE ALL ON FUNCTION {GUARD}() FROM PUBLIC")
    op.execute(f'REVOKE ALL ON FUNCTION {GUARD}() FROM "{role}"')
    op.execute(f"REVOKE ALL ON TABLE {TABLE} FROM PUBLIC")
    op.execute(f'REVOKE ALL ON TABLE {TABLE} FROM "{role}"')
    op.execute(f'GRANT SELECT ON TABLE {TABLE} TO "{role}"')
    op.execute(f'GRANT INSERT ({", ".join(INSERT_COLUMNS)}) ON TABLE {TABLE} TO "{role}"')
    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    op.execute(
        f"""
        DO $down$
        DECLARE
            n BIGINT;
        BEGIN
            EXECUTE 'LOCK TABLE {TABLE} IN ACCESS EXCLUSIVE MODE';
            EXECUTE 'SELECT count(*) FROM {TABLE}' INTO n;
            IF n > 0 THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: % stored level watches', n
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
        END
        $down$;
        """  # noqa: S608 - constant names only
    )
    role = _BASE._app_role()
    op.execute(previous_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {_BASE.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"DROP TABLE {TABLE}")
    op.execute(f"DROP FUNCTION {GUARD}()")
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
