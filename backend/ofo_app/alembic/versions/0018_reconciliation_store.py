"""Reconciliation store: stored mismatches, recorded resolutions, standalone quantities (#380 step 2.1).

Basis: REQ-060 AC-6 ("While a mismatch is unresolved, new execution and adjustment execution are blocked (Q199).");
Q222 (owner-confirmed 2026-09-29: "an agreeing reconciliation run does not unblock a strategy by itself; the block
lifts only through a recorded manual resolution"); REQ-060 AC-5 (manual reconciliation is explicit and audited);
REQ-060 AC-7 (standalone positions are recorded with their quantity); ADR-109 (1) ("a stored, sticky mismatch
block") and (4) (the first reconcile screen's three actions); ADR-048 (the limited application role); ADR-023 (the
database clock).

Copy from: none - modelled on 0016's tables, guards, grants and allow-list block.

Changes (owner-run, one transaction):
- public.reconciliation_mismatches: one row per detected mismatch of one strategy on one contract (contract key =
  the app's instrument id "<segment>:<exchange token>"), the expected and Zerodha net units (they differ: an agreeing
  comparison is not a mismatch), the raw report (a JSON object, size-capped), the trigger source from a closed list,
  detected_at from the database clock. Guard trigger (SQLSTATE OF018): insert-only, never updated or deleted.
- public.reconciliation_resolutions: the action from a closed list (ADR-109 (4)'s three, plus attach/detach reserved
  for the later release), the actor, an optional note, resolved_at from the database clock. One row per mismatch and
  action (PRIMARY KEY mismatch_id, action) and at most one SETTLING row per mismatch (unique index on mismatch_id for
  every action but ``marked_requiring_attention``): a mark "requiring attention" settles nothing and does not lift the
  block (ADR-018 Q198, Q222), so the mismatch can still be settled after it. Guard trigger (OF018): insert-only.
- public.reconciliation_standalone: per user + contract, the signed units left standalone (0 allowed); the only
  UPDATE changes units (updated_at from the clock); never deleted.
- public.execution_plans' close-reason CHECK gains ``unresolved_from_positions`` (an earlier-day plan the next-day
  positions cannot settle closes, and the mismatch record carries the block). No pinned function body changes.
- Grants (column-limited): SELECT on the three tables; INSERT on the written columns (never the clock columns or the
  id); UPDATE (units) on the standalone table only; USAGE on the mismatch id sequence. No DELETE or TRUNCATE.
- public.ofo_assert_app_role_allowlist: 0017's text plus block 16 for the three tables.
- downgrade: refuses while any row is stored in the three tables or any plan is closed ``unresolved_from_positions``;
  otherwise restores 0017's state exactly.

Revision ID: 0018_reconciliation_store
Revises: 0017_audit_order_prepared
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0018_reconciliation_store"
down_revision = "0017_audit_order_prepared"
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


_PREVIOUS = _load(f"{down_revision}.py", "ofo_migration_predecessor_for_0018")
_M16 = _PREVIOUS._PREVIOUS  # 0016
_M8 = _M16._M8
_M4 = _M16._M4
_M3 = _M16._M3
_PREV = _M16._PREV  # 0002
_BASE = _PREVIOUS._BASE  # 0001

SEARCH_PATH = _M16.SEARCH_PATH
SQLSTATE = "OF018"
MISMATCHES = "public.reconciliation_mismatches"
MISMATCH_SEQUENCE = "public.reconciliation_mismatches_id_seq"
RESOLUTIONS = "public.reconciliation_resolutions"
STANDALONE = "public.reconciliation_standalone"
MISMATCH_GUARD = "public.reconciliation_mismatches_guard"
RESOLUTION_GUARD = "public.reconciliation_resolutions_guard"
STANDALONE_GUARD = "public.reconciliation_standalone_guard"
MISMATCH_TRIGGER = "reconciliation_mismatches_guard"
RESOLUTION_TRIGGER = "reconciliation_resolutions_guard"
STANDALONE_TRIGGER = "reconciliation_standalone_guard"
PLANS = _M16.PLANS
PLAN_REASON_CHECK = "execution_plans_close_reason_check"  # PostgreSQL's name for 0016's unnamed column CHECK
NEW_REASON = "unresolved_from_positions"
REASONS_BEFORE = _M16.REASONS
REASONS_AFTER = (*REASONS_BEFORE, NEW_REASON)
#: The trigger sources (ofo.reconciliation.triggers.Trigger names, lower case) plus the next-day plan resolution.
SOURCES = ("after_execution", "after_reconnect", "app_start", "app_resume", "periodic", "broker_position_event",
           "order_event", "next_day_resolution")
#: ADR-109 (4)'s three first actions, then attach/detach outside lots (ADR-109 (2), a later release).
ACTIONS = ("reconciled_by_basket", "marked_requiring_attention", "kite_flat_marked_exited", "attached_outside",
           "detached_outside")
ATTENTION = "marked_requiring_attention"  # recorded, settles nothing: never lifts a block (ADR-018 Q198, Q222)
SETTLED_INDEX = "reconciliation_resolutions_one_settling"
MAX_UNITS = 1_000_000  # ofo.strategy.definition.MAX_UNITS (a migration carries its own literal)
MAX_REPORT_BYTES = 65_536
MAX_TEXT = 500
CONTRACT_KEY_REGEX = "^[A-Z][A-Z0-9-]{0,15}:[1-9][0-9]{0,18}$"  # "<segment>:<exchange token>", e.g. NFO-OPT:47189
MISMATCH_INSERT_COLUMNS = ("strategy_id", "contract_key", "expected_units", "zerodha_units", "report", "source")
RESOLUTION_INSERT_COLUMNS = ("mismatch_id", "action", "actor", "note")
STANDALONE_INSERT_COLUMNS = ("user_ref", "contract_key", "units")
STANDALONE_UPDATE_COLUMNS = ("units",)
ALLOWLIST_BLOCK_MARKER = "-- 16. reconciliation store"


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _insert_only_guard_sql(fn: str, what: str, clock_column: str) -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {fn}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION '{what} are insert-only' USING ERRCODE = '{SQLSTATE}';
            END IF;
            NEW.{clock_column} := clock_timestamp();
            RETURN NEW;
        END
        $fn$
        """


def _mismatch_guard_sql() -> str:
    return _insert_only_guard_sql(MISMATCH_GUARD, "reconciliation mismatches", "detected_at")


def _resolution_guard_sql() -> str:
    return _insert_only_guard_sql(RESOLUTION_GUARD, "reconciliation resolutions", "resolved_at")


def _standalone_guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {STANDALONE_GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'standalone quantities are never deleted' USING ERRCODE = '{SQLSTATE}';
            END IF;
            IF TG_OP = 'UPDATE' AND (NEW.user_ref <> OLD.user_ref OR NEW.contract_key <> OLD.contract_key) THEN
                RAISE EXCEPTION 'a standalone quantity only changes its units' USING ERRCODE = '{SQLSTATE}';
            END IF;
            NEW.updated_at := clock_timestamp();
            RETURN NEW;
        END
        $fn$
        """


MISMATCH_PIN = _M4._md5_body(_mismatch_guard_sql())
RESOLUTION_PIN = _M4._md5_body(_resolution_guard_sql())
STANDALONE_PIN = _M4._md5_body(_standalone_guard_sql())


def _table_block(table: str, label: str, insert_cols, update_cols, guard: str, trigger: str, pin: str,
                 sequence: str = "") -> str:
    sequence_checks = _M3._sequence_checks(sequence, f"{label} id", usage=True) if sequence else ""
    return f"""        IF to_regclass('{table}') IS NULL THEN
            problems := problems || 'table {table} is missing'::TEXT;
        ELSE
            IF (SELECT relowner FROM pg_class WHERE oid = '{table}'::regclass)
               IS DISTINCT FROM (SELECT relowner FROM pg_class WHERE oid = '{_M3.TABLE}'::regclass) THEN
                problems := problems || 'table {table} is not owned by the catalogue table owner'::TEXT;
            END IF;
{_PREV._privilege_checks(table, label, {"SELECT"})}
{_M3._columns_exactly(table, label, "INSERT", insert_cols)}
{_M3._columns_exactly(table, label, "UPDATE", update_cols)}
{sequence_checks}
{_M3._guard_function_checks(guard, security_definer=False)}
{_M8._trigger_check(table, trigger, guard, pin)}
        END IF;"""  # noqa: S608 constant table names


def _block() -> str:
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (#380 step 2.1): reconciliation_mismatches, reconciliation_resolutions and
    --    reconciliation_standalone: SELECT, column-limited INSERT / UPDATE exactly as granted, no DELETE / TRUNCATE;
    --    the guard triggers enabled with their pinned bodies, no EXECUTE on a guard
    IF phase = 'post' THEN
{_table_block(MISMATCHES, "reconciliation_mismatches", MISMATCH_INSERT_COLUMNS, (), MISMATCH_GUARD, MISMATCH_TRIGGER,
              MISMATCH_PIN, MISMATCH_SEQUENCE)}
{_table_block(RESOLUTIONS, "reconciliation_resolutions", RESOLUTION_INSERT_COLUMNS, (), RESOLUTION_GUARD,
              RESOLUTION_TRIGGER, RESOLUTION_PIN)}
{_table_block(STANDALONE, "reconciliation_standalone", STANDALONE_INSERT_COLUMNS, STANDALONE_UPDATE_COLUMNS,
              STANDALONE_GUARD, STANDALONE_TRIGGER, STANDALONE_PIN)}
    END IF;
"""


_INSERT_BEFORE = _PREV._INSERT_BEFORE


def previous_allowlist_sql() -> str:
    return _PREVIOUS.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """0017's allowlist text plus block 16. Fails closed (RuntimeError) on a changed shape or a block 16 already in."""
    previous = previous_allowlist_sql()
    headers = previous.count("CREATE FUNCTION") + previous.count("CREATE OR REPLACE FUNCTION")
    if headers != 1 or previous.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the reconciliation store checks safely")
    sql = previous.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    return sql.replace(_INSERT_BEFORE, _block() + _INSERT_BEFORE, 1)


def reason_check_sql(reasons: tuple[str, ...]) -> list[str]:
    return [
        f"ALTER TABLE {PLANS} DROP CONSTRAINT {PLAN_REASON_CHECK}",
        f"ALTER TABLE {PLANS} ADD CONSTRAINT {PLAN_REASON_CHECK} CHECK (close_reason IN ({_quoted(reasons)}))",
    ]


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    for statement in reason_check_sql(REASONS_AFTER):
        op.execute(statement)
    op.execute(
        f"""
        CREATE TABLE {MISMATCHES} (
            id             BIGSERIAL   PRIMARY KEY,
            strategy_id    BIGINT      NOT NULL REFERENCES public.strategies (id),
            contract_key   TEXT        NOT NULL CHECK (contract_key ~ '{CONTRACT_KEY_REGEX}'),
            expected_units INTEGER     NOT NULL CHECK (expected_units BETWEEN -{MAX_UNITS} AND {MAX_UNITS}),
            zerodha_units  INTEGER     NOT NULL CHECK (zerodha_units BETWEEN -{MAX_UNITS} AND {MAX_UNITS}),
            report         JSONB       NOT NULL CHECK (jsonb_typeof(report) = 'object'
                                                       AND octet_length(report::text) <= {MAX_REPORT_BYTES}),
            source         TEXT        NOT NULL CHECK (source IN ({_quoted(SOURCES)})),
            detected_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            CHECK (expected_units <> zerodha_units)
        )
        """
    )
    op.execute(f"CREATE INDEX reconciliation_mismatches_strategy ON {MISMATCHES} (strategy_id)")
    op.execute(
        f"""
        CREATE TABLE {RESOLUTIONS} (
            mismatch_id BIGINT      NOT NULL REFERENCES {MISMATCHES} (id),
            action      TEXT        NOT NULL CHECK (action IN ({_quoted(ACTIONS)})),
            actor       TEXT        NOT NULL CHECK (actor <> '' AND length(actor) <= {MAX_TEXT}),
            note        TEXT        CHECK (note IS NULL OR (note <> '' AND length(note) <= {MAX_TEXT})),
            resolved_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (mismatch_id, action)
        )
        """
    )
    op.execute(f"CREATE UNIQUE INDEX {SETTLED_INDEX} ON {RESOLUTIONS} (mismatch_id) "
               f"WHERE action <> '{ATTENTION}'")
    op.execute(
        f"""
        CREATE TABLE {STANDALONE} (
            user_ref     TEXT        NOT NULL CHECK (user_ref <> '' AND length(user_ref) <= {MAX_TEXT}),
            contract_key TEXT        NOT NULL CHECK (contract_key ~ '{CONTRACT_KEY_REGEX}'),
            units        INTEGER     NOT NULL CHECK (units BETWEEN -{MAX_UNITS} AND {MAX_UNITS}),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (user_ref, contract_key)
        )
        """
    )
    op.execute(_mismatch_guard_sql())
    op.execute(_resolution_guard_sql())
    op.execute(_standalone_guard_sql())
    for table, guard, trigger in ((MISMATCHES, MISMATCH_GUARD, MISMATCH_TRIGGER),
                                  (RESOLUTIONS, RESOLUTION_GUARD, RESOLUTION_TRIGGER),
                                  (STANDALONE, STANDALONE_GUARD, STANDALONE_TRIGGER)):
        op.execute(f"CREATE TRIGGER {trigger} BEFORE INSERT OR UPDATE OR DELETE ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION {guard}()")
        op.execute(f"REVOKE ALL ON FUNCTION {guard}() FROM PUBLIC")
        op.execute(f'REVOKE ALL ON FUNCTION {guard}() FROM "{role}"')
    for table, insert_cols, update_cols in ((MISMATCHES, MISMATCH_INSERT_COLUMNS, ()),
                                            (RESOLUTIONS, RESOLUTION_INSERT_COLUMNS, ()),
                                            (STANDALONE, STANDALONE_INSERT_COLUMNS, STANDALONE_UPDATE_COLUMNS)):
        op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
        op.execute(f'REVOKE ALL ON TABLE {table} FROM "{role}"')
        op.execute(f'GRANT SELECT ON TABLE {table} TO "{role}"')
        op.execute(f'GRANT INSERT ({", ".join(insert_cols)}) ON TABLE {table} TO "{role}"')
        if update_cols:
            op.execute(f'GRANT UPDATE ({", ".join(update_cols)}) ON TABLE {table} TO "{role}"')
    op.execute(f"REVOKE ALL ON SEQUENCE {MISMATCH_SEQUENCE} FROM PUBLIC")
    op.execute(f'REVOKE ALL ON SEQUENCE {MISMATCH_SEQUENCE} FROM "{role}"')
    op.execute(f'GRANT USAGE ON SEQUENCE {MISMATCH_SEQUENCE} TO "{role}"')
    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    # Mismatches and resolutions are the audit of a block: refuse rather than drop them.
    op.execute(
        f"""
        DO $down$
        BEGIN
            EXECUTE 'LOCK TABLE {MISMATCHES}, {RESOLUTIONS}, {STANDALONE}, {PLANS} IN ACCESS EXCLUSIVE MODE';
            IF EXISTS (SELECT 1 FROM {MISMATCHES}) OR EXISTS (SELECT 1 FROM {RESOLUTIONS})
               OR EXISTS (SELECT 1 FROM {STANDALONE})
               OR EXISTS (SELECT 1 FROM {PLANS} WHERE close_reason = '{NEW_REASON}') THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: reconciliation records are stored';
            END IF;
        END
        $down$;
        """  # noqa: S608 constant table names
    )
    role = _BASE._app_role()
    op.execute(previous_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {_BASE.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"DROP TABLE {RESOLUTIONS}")
    op.execute(f"DROP TABLE {MISMATCHES}")
    op.execute(f"DROP TABLE {STANDALONE}")
    op.execute(f"DROP FUNCTION {MISMATCH_GUARD}()")
    op.execute(f"DROP FUNCTION {RESOLUTION_GUARD}()")
    op.execute(f"DROP FUNCTION {STANDALONE_GUARD}()")
    for statement in reason_check_sql(REASONS_BEFORE):
        op.execute(statement)
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
