"""Each strategy's entry facts, written ONCE at its first fill (contract "Your adjustment settings" step 2; ADR-243).

Spec basis: ADR-243 ("Entry distance from spot" (Q255): keep widths, re-place the short at its entry distance from
spot, snapped to a listed strike; "needs each strategy's entry spot stored"); REQ-046 Q255 example (entered 353 above
spot 23,047; spot 23,300 -> 23,650 / 23,850); ADR-048 (the limited application role); ADR-023 (database clock).
TECHNICAL DECISION (orchestrator 2026-11-05): the entry spot AND each side's entry distance are stored at the first
fill; the placement reads the stored distance, never the current strike's (after a second roll it would inflate).

Copy from: 0038_strategy_level_watch.py (insert-only guard, statement-level truncate trigger, grants, allow-list block).

Changes (owner-run, one transaction; ADDITIVE: a new table, no existing table or row changed, no back-fill):
- public.strategy_entry_facts: strategy_id (a stored strategy, PRIMARY KEY: one row per strategy, ever), entry_spot
  NUMERIC > 0, call_distance NUMERIC NULL, put_distance NUMERIC NULL (NULL = no short on that side at entry),
  created_at DEFAULT clock_timestamp(). A strategy filled before this migration has no row: under "Entry distance"
  its rolls are refused with a named reason (fail closed).
- Insert-only guard (BEFORE INSERT OR UPDATE OR DELETE, SQLSTATE OF039, search_path pinned, md5-pinned in the
  allow-list): every UPDATE and DELETE is refused, so the facts are never rewritten; the same function on a
  statement-level BEFORE TRUNCATE trigger refuses TRUNCATE.
- Grants: the application role gets SELECT and column INSERT on strategy_id, entry_spot, call_distance, put_distance.
- public.ofo_assert_app_role_allowlist: 0038's chain text plus block 31.
- downgrade: refuses (OF039) while any row exists.

Known bypasses (out of the threat model): the table owner or a superuser can drop or disable the guard, then edit rows.

Revision ID: 0039_strategy_entry_facts
Revises: 0038_strategy_level_watch
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0039_strategy_entry_facts"
down_revision = "0038_strategy_level_watch"
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


_M38 = _load("0038_strategy_level_watch.py", "ofo_migration_0038_for_0039")
_M37 = _M38._M37
_M36 = _M37._M36
_M35 = _M36._M35
_M16 = _M35._M16
_M4 = _M35._M4
_BASE = _M35._BASE
_INSERT_BEFORE = _M35._INSERT_BEFORE

SEARCH_PATH = _M16.SEARCH_PATH
SQLSTATE = "OF039"  # an update, a delete or a truncate of stored entry facts

TABLE = "public.strategy_entry_facts"
GUARD = "public.strategy_entry_facts_guard"
TRIGGER = "strategy_entry_facts_guard"
TRUNCATE_TRIGGER = "strategy_entry_facts_no_truncate"
LABEL = "strategy_entry_facts"
INSERT_COLUMNS = ("strategy_id", "entry_spot", "call_distance", "put_distance")
NO_UPDATE: tuple[str, ...] = ()
ALLOWLIST_BLOCK_MARKER = "-- 31. strategy entry facts"


def _guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'entry facts are written once at the first fill and never changed'
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
    {ALLOWLIST_BLOCK_MARKER} (ADR-243 entry facts): SELECT + column INSERT on {", ".join(INSERT_COLUMNS)} only;
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
    return _M38.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """0038's chain text plus block 31. Fails closed (RuntimeError) on a changed shape or a block 30 already in."""
    previous = previous_allowlist_sql()
    if previous.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous or "-- 31." in previous:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the entry-facts checks safely")
    return previous.replace(_INSERT_BEFORE, _block() + _INSERT_BEFORE, 1)


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(
        f"""
        CREATE TABLE {TABLE} (
            strategy_id   BIGINT      PRIMARY KEY REFERENCES public.strategies (id),
            entry_spot    NUMERIC     NOT NULL CHECK (entry_spot > 0),
            call_distance NUMERIC     NULL,
            put_distance  NUMERIC     NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
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
                RAISE EXCEPTION 'refusing to downgrade {revision}: % stored entry facts', n
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
