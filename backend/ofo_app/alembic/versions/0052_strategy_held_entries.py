"""A strategy entered "held at my broker": the stated entry time and the broker's name (GC-TRACK1 k06; ADR-292 (1)(2)).

Spec basis: ADR-292 (2) ("it may be earlier than now, never in the future, and never after the expiry of any of its
legs ... A broker name is optional free text, shown and never used"); ADR-290 (2); ADR-291; ADR-048 (limited app role).
Copy from: 0050_strategy_basket_facts.py (a new insert-only table, its guard, truncate trigger, allow-list block).
A separate table, not a column of public.strategies (its guard refuses changes to fixed columns).

Changes (owner-run, one transaction; ADDITIVE: a new table, no existing table or row changed, no back-fill):
- public.strategy_held_entries: strategy_id PRIMARY KEY (one row per strategy), entry_at TIMESTAMPTZ (the user's stated
  time), broker_text NULL (1 to 40 characters, no line break), created_at DEFAULT clock_timestamp(),
  CHECK (entry_at <= created_at).
- Insert-only guard (SQLSTATE OF052, search_path pinned, md5-pinned in the allow-list) + statement-level truncate.
- Grants: SELECT and column INSERT on strategy_id, entry_at, broker_text.
- public.ofo_assert_app_role_allowlist: 0050's chain text plus block 35.
- downgrade: refuses (OF052) while any row exists.

Revision ID: 0052_strategy_held_entries
Revises: 0051_trigger_label_words
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0052_strategy_held_entries"
down_revision = "0051_trigger_label_words"
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


_M39 = _load("0039_strategy_entry_facts.py", "ofo_migration_0039_for_0052")
_M50 = _load("0050_strategy_basket_facts.py", "ofo_migration_0050_for_0052")
_M35 = _M39._M35
_M16 = _M39._M16
_M4 = _M39._M4
_BASE = _M39._BASE
_INSERT_BEFORE = _M39._INSERT_BEFORE

SEARCH_PATH = _M16.SEARCH_PATH
SQLSTATE = "OF052"  # an update, a delete or a truncate of stored held entries

TABLE = "public.strategy_held_entries"
GUARD = "public.strategy_held_entries_guard"
TRIGGER = "strategy_held_entries_guard"
TRUNCATE_TRIGGER = "strategy_held_entries_no_truncate"
LABEL = "strategy_held_entries"
INSERT_COLUMNS = ("strategy_id", "entry_at", "broker_text")
NO_UPDATE: tuple[str, ...] = ()
ALLOWLIST_BLOCK_MARKER = "-- 35. strategy held entries"


def _guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'a held entry is written once with its first basket and never changed'
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
            RETURN NEW;
        END
        $fn$
        """


PIN = _M4._md5_body(_guard_sql())


def _trigger_checks() -> str:
    """0039's check shape, for this table's two triggers."""
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
                  OR (SELECT tgtype::int {row}) IS DISTINCT FROM {_M35.BEFORE_STATEMENT_TRUNCATE}
                  OR (SELECT tgqual IS NOT NULL OR tgattr::text <> '' OR tgnargs <> 0 {row}) THEN
                problems := problems || 'trigger {TRUNCATE_TRIGGER} is not a plain BEFORE TRUNCATE trigger'::TEXT;
            END IF;"""  # noqa: S608 - constant names only


def _block() -> str:
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (ADR-292 held entries): SELECT + column INSERT on {", ".join(INSERT_COLUMNS)} only;
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
    return _M50.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """0050's chain text plus block 35. Fails closed (RuntimeError) on a changed shape or a block 35 already in."""
    previous = previous_allowlist_sql()
    if previous.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous or "-- 35." in previous:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the held-entries checks safely")
    return previous.replace(_INSERT_BEFORE, _block() + _INSERT_BEFORE, 1)


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(
        f"""
        CREATE TABLE {TABLE} (
            strategy_id BIGINT      NOT NULL PRIMARY KEY REFERENCES public.strategies (id),
            entry_at    TIMESTAMPTZ NOT NULL,
            broker_text TEXT        NULL CHECK (char_length(broker_text) BETWEEN 1 AND 40
                                         AND position(chr(10) in broker_text) = 0
                                         AND position(chr(13) in broker_text) = 0),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            CHECK (entry_at <= created_at)
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
                RAISE EXCEPTION 'refusing to downgrade {revision}: % stored held entries', n
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
