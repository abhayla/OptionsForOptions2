"""Each strategy's market state at every basket's fill: the rule starting point (ADR-283 (1); GC-ICGUIDE g32 fx1).

Spec basis: ADR-283 (1) ("the starting point of every playbook rule after the entry and after each adjustment basket N
is the market state at that basket's fill (order clock, spot, ATM IV and every open leg's price), stored with the fill
in the same transaction, like the entry facts (ADR-243)"); ADR-258; ADR-255 (the basket count); ADR-048; ADR-008.
Copy from: 0039_strategy_entry_facts.py (the table, its insert-only guard, its truncate trigger, its allow-list block).

Changes (owner-run, one transaction; ADDITIVE: a new table, no existing table or row changed, no back-fill):
- public.strategy_basket_facts: (strategy_id, basket_no) PRIMARY KEY (basket_no = adjustments made so far after the
  basket, ADR-255; 0 = the entry), clock TIMESTAMPTZ (the order clock: the scenario clock in test-data mode), spot
  NUMERIC > 0, atm_iv NUMERIC NULL > 0, legs JSONB (array: every open leg with its price at the fill, a price NULL when
  not read), created_at DEFAULT clock_timestamp(). A basket filled before this migration has no row: nothing is held.
- Insert-only guard (SQLSTATE OF050, search_path pinned, md5-pinned in the allow-list) + statement-level truncate.
- Grants: SELECT and column INSERT on strategy_id, basket_no, clock, spot, atm_iv, legs.
- public.ofo_assert_app_role_allowlist: 0049's chain text plus block 34.
- downgrade: refuses (OF050) while any row exists.

Revision ID: 0050_strategy_basket_facts
Revises: 0049_strategy_closed_status
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0050_strategy_basket_facts"
down_revision = "0049_strategy_closed_status"
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


_M39 = _load("0039_strategy_entry_facts.py", "ofo_migration_0039_for_0050")
_M49 = _load("0049_strategy_closed_status.py", "ofo_migration_0049_for_0050")
_M35 = _M39._M35
_M16 = _M39._M16
_M4 = _M39._M4
_BASE = _M39._BASE
_INSERT_BEFORE = _M39._INSERT_BEFORE

SEARCH_PATH = _M16.SEARCH_PATH
SQLSTATE = "OF050"  # an update, a delete or a truncate of stored basket facts

TABLE = "public.strategy_basket_facts"
GUARD = "public.strategy_basket_facts_guard"
TRIGGER = "strategy_basket_facts_guard"
TRUNCATE_TRIGGER = "strategy_basket_facts_no_truncate"
LABEL = "strategy_basket_facts"
INSERT_COLUMNS = ("strategy_id", "basket_no", "clock", "spot", "atm_iv", "legs")
NO_UPDATE: tuple[str, ...] = ()
ALLOWLIST_BLOCK_MARKER = "-- 34. strategy basket facts"


def _guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'basket facts are written once at the basket fill and never changed'
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
    {ALLOWLIST_BLOCK_MARKER} (ADR-283 basket facts): SELECT + column INSERT on {", ".join(INSERT_COLUMNS)} only;
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
    return _M49.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """0049's chain text plus block 34. Fails closed (RuntimeError) on a changed shape or a block 34 already in."""
    previous = previous_allowlist_sql()
    if previous.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous or "-- 34." in previous:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the basket-facts checks safely")
    return previous.replace(_INSERT_BEFORE, _block() + _INSERT_BEFORE, 1)


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(
        f"""
        CREATE TABLE {TABLE} (
            strategy_id BIGINT      NOT NULL REFERENCES public.strategies (id),
            basket_no   INTEGER     NOT NULL CHECK (basket_no >= 0),
            clock       TIMESTAMPTZ NOT NULL,
            spot        NUMERIC     NOT NULL CHECK (spot > 0),
            atm_iv      NUMERIC     NULL CHECK (atm_iv > 0),
            legs        JSONB       NOT NULL CHECK (jsonb_typeof(legs) = 'array'),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (strategy_id, basket_no)
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
                RAISE EXCEPTION 'refusing to downgrade {revision}: % stored basket facts', n
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
