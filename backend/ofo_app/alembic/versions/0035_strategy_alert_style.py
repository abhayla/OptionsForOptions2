"""A user's alert-style pin per strategy as dated, append-only rows (REQ-170 Q-AD-2, AC-6; GC-ALERT1 item 4).

Spec basis: REQ-170 Q-AD-2 "the style is taken from the strategy and changes by itself as expiry nears ... the user
may pin a style per strategy"; REQ-168 AC-3 "every read and write is keyed by the user"; ADR-048 (the limited
application role); ADR-023 (database clock).

Copy from: 0033_user_adjustment_preferences.py (append-only guard, statement-level truncate trigger, grants, allow-list
block) keyed by the user and the strategy.

Changes (owner-run, one transaction):
- public.strategy_alert_style: user_ref (non-empty, at most 200), strategy_id (a stored strategy), style NULL
  (= automatic: the resolver ``alert_presets.style_for`` picks it from the expiry) or one of intraday / weekly /
  monthly, effective_from TIMESTAMPTZ, created_at DEFAULT clock_timestamp().
  PRIMARY KEY (user_ref, strategy_id, effective_from). The pin in force is the newest row.
- Append-only guard (BEFORE INSERT OR UPDATE OR DELETE, SQLSTATE OF035, search_path pinned, md5-pinned in the
  allow-list): every UPDATE and DELETE is refused (a change, or a return to automatic, is a new row); an INSERT more
  than 5 seconds in the past is refused (back-dated); the same function on a statement-level BEFORE TRUNCATE trigger
  refuses TRUNCATE.
- Grants: the application role gets SELECT and column INSERT on user_ref, strategy_id, style, effective_from.
- public.ofo_assert_app_role_allowlist: 0034's chain text plus block 27.
- downgrade: refuses (OF035) while any row exists.

Known bypasses (out of the threat model): the table owner or a superuser can drop or disable the guard, then edit rows.

Revision ID: 0035_strategy_alert_style
Revises: 0034_system_playbook_versions
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0035_strategy_alert_style"
down_revision = "0034_system_playbook_versions"
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


_M34 = _load("0034_system_playbook_versions.py", "ofo_migration_0034_for_0035")
_M33 = _M34._M33
_M16 = _M34._M16
_M4 = _M34._M4
_BASE = _M34._BASE
_INSERT_BEFORE = _M34._INSERT_BEFORE

SEARCH_PATH = _M16.SEARCH_PATH
SQLSTATE = "OF035"  # an update, a delete, a truncate or a back-dated insert of a stored alert-style pin
BACKDATE_GRACE_SECONDS = _M33.BACKDATE_GRACE_SECONDS

TABLE = "public.strategy_alert_style"
GUARD = "public.strategy_alert_style_guard"
TRIGGER = "strategy_alert_style_guard"
TRUNCATE_TRIGGER = "strategy_alert_style_no_truncate"
LABEL = "strategy_alert_style"
STYLES = ("intraday", "weekly", "monthly")  # alert_presets.STYLES (a test asserts they are equal)
USER_MAX = _M33.USER_MAX
INSERT_COLUMNS = ("user_ref", "strategy_id", "style", "effective_from")
NO_UPDATE: tuple[str, ...] = ()
ALLOWLIST_BLOCK_MARKER = "-- 27. strategy alert style"


def _guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'alert-style pins are insert-only: a change or a return to automatic is a new row'
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
            IF NEW.effective_from < clock_timestamp() - interval '{BACKDATE_GRACE_SECONDS} seconds' THEN
                RAISE EXCEPTION 'an alert-style pin takes effect now: a back-dated row is refused'
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
            RETURN NEW;
        END
        $fn$
        """


PIN = _M4._md5_body(_guard_sql())
BEFORE_STATEMENT_TRUNCATE = _M34.BEFORE_STATEMENT_TRUNCATE


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
    {ALLOWLIST_BLOCK_MARKER} (REQ-170): SELECT + column INSERT on {", ".join(INSERT_COLUMNS)} only;
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
    return _M34.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """0034's chain text plus block 27. Fails closed (RuntimeError) on a changed shape or a block 27 already in."""
    previous = previous_allowlist_sql()
    if previous.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous or "-- 27." in previous:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the alert-style checks safely")
    return previous.replace(_INSERT_BEFORE, _block() + _INSERT_BEFORE, 1)


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    styles = ", ".join(f"'{s}'" for s in STYLES)
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(
        f"""
        CREATE TABLE {TABLE} (
            user_ref       TEXT        NOT NULL CHECK (btrim(user_ref) <> '' AND length(user_ref) <= {USER_MAX}),
            strategy_id    BIGINT      NOT NULL REFERENCES public.strategies (id),
            style          TEXT        NULL CHECK (style IS NULL OR style IN ({styles})),
            effective_from TIMESTAMPTZ NOT NULL,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (user_ref, strategy_id, effective_from)
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
                RAISE EXCEPTION 'refusing to downgrade {revision}: % stored alert-style rows', n
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
