"""Paper stop-loss triggers and the alerts they raise (GC-TP step 7a).

Basis: REQ-109 AC-8 ("fires each trigger once (also across a restart)"); ADR-207 (5) (paper stop-loss: a Conditional
Exit on the index and a per-leg stop, Sensibull screens 221-224); ADR-048 (the limited application role); ADR-023 (the
database clock); money and levels NUMERIC(14,2) (decimal-money-boundaries).

Copy from: none - modelled on 0028's table, guard trigger, grants and allow-list block.

Changes (owner-run, one transaction, the API stopped):
- public.paper_triggers: id BIGSERIAL, strategy_id -> strategies, kind conditional_exit|leg_stop, contract_id ->
  catalogue_contracts (NULL for conditional_exit, NOT NULL for leg_stop), underlying (the index's name, NOT NULL for
  conditional_exit, NULL for leg_stop), direction above|below, level NUMERIC(14,2) > 0, created_at from the database
  clock, fired_at NULL, cancelled_at NULL; never both fired and cancelled.
- Guard (SQLSTATE OF029): no DELETE; an INSERT starts armed (fired_at and cancelled_at NULL); an UPDATE may change only
  fired_at and cancelled_at, and each only from NULL (a fire or a cancel is written once and never undone).
- public.paper_alerts: id BIGSERIAL, strategy_id -> strategies, trigger_id -> paper_triggers, created_at, title, body,
  read_at NULL. Guard (same SQLSTATE): no DELETE; an INSERT starts unread; an UPDATE may set only read_at, from NULL.
- Grants: the application role gets SELECT, column-limited INSERT and UPDATE (fired_at, cancelled_at / read_at); no
  DELETE or TRUNCATE; USAGE on both sequences.
- public.ofo_assert_app_role_allowlist: the predecessor's chain text plus block 22.
- downgrade: drops both tables (alerts first) and restores the predecessor's allow-list. A fired trigger's stop orders
  stay in paper_orders (their trigger_id then names no row; it never had a foreign key).

Revision ID: 0029_paper_triggers
Revises: 0028_paper_orders
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0029_paper_triggers"
down_revision = "0028_paper_orders"
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


_PREVIOUS = _load(f"{down_revision}.py", "ofo_migration_predecessor_for_0029")  # 0028
_M16 = _PREVIOUS._M16
_M4 = _PREVIOUS._M4
_BASE = _PREVIOUS._BASE
_INSERT_BEFORE = _PREVIOUS._INSERT_BEFORE

SEARCH_PATH = _M16.SEARCH_PATH
SQLSTATE = "OF029"
TRIGGERS = "public.paper_triggers"
ALERTS = "public.paper_alerts"
TRIGGERS_GUARD = "public.paper_triggers_guard"
ALERTS_GUARD = "public.paper_alerts_guard"
TRIGGERS_TRIGGER = "paper_triggers_guard"
ALERTS_TRIGGER = "paper_alerts_guard"
TRIGGERS_SEQUENCE = "public.paper_triggers_id_seq"
ALERTS_SEQUENCE = "public.paper_alerts_id_seq"
KINDS = ("conditional_exit", "leg_stop")
DIRECTIONS = ("above", "below")
TRIGGER_INSERT_COLUMNS = ("strategy_id", "kind", "contract_id", "underlying", "direction", "level")
TRIGGER_UPDATE_COLUMNS = ("fired_at", "cancelled_at")
ALERT_INSERT_COLUMNS = ("strategy_id", "trigger_id", "title", "body")
ALERT_UPDATE_COLUMNS = ("read_at",)
ALLOWLIST_BLOCK_MARKER = "-- 22. paper triggers"


def _triggers_guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {TRIGGERS_GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'paper triggers are never deleted' USING ERRCODE = '{SQLSTATE}';
            END IF;
            IF TG_OP = 'INSERT' THEN
                IF NEW.fired_at IS NOT NULL OR NEW.cancelled_at IS NOT NULL THEN
                    RAISE EXCEPTION 'a paper trigger starts armed' USING ERRCODE = '{SQLSTATE}';
                END IF;
                RETURN NEW;
            END IF;
            IF (NEW.id, NEW.strategy_id, NEW.kind, NEW.contract_id, NEW.underlying, NEW.direction, NEW.level,
                NEW.created_at)
               IS DISTINCT FROM (OLD.id, OLD.strategy_id, OLD.kind, OLD.contract_id, OLD.underlying, OLD.direction,
                                 OLD.level, OLD.created_at) THEN
                RAISE EXCEPTION 'only fired_at and cancelled_at of a paper trigger may change'
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
            IF (OLD.fired_at IS NOT NULL AND NEW.fired_at IS DISTINCT FROM OLD.fired_at)
               OR (OLD.cancelled_at IS NOT NULL AND NEW.cancelled_at IS DISTINCT FROM OLD.cancelled_at) THEN
                RAISE EXCEPTION 'a paper trigger is fired or cancelled once' USING ERRCODE = '{SQLSTATE}';
            END IF;
            RETURN NEW;
        END
        $fn$
        """


def _alerts_guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {ALERTS_GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'paper alerts are never deleted' USING ERRCODE = '{SQLSTATE}';
            END IF;
            IF TG_OP = 'INSERT' THEN
                IF NEW.read_at IS NOT NULL THEN
                    RAISE EXCEPTION 'a paper alert starts unread' USING ERRCODE = '{SQLSTATE}';
                END IF;
                RETURN NEW;
            END IF;
            IF (NEW.id, NEW.strategy_id, NEW.trigger_id, NEW.created_at, NEW.title, NEW.body)
               IS DISTINCT FROM (OLD.id, OLD.strategy_id, OLD.trigger_id, OLD.created_at, OLD.title, OLD.body)
               OR (OLD.read_at IS NOT NULL AND NEW.read_at IS DISTINCT FROM OLD.read_at) THEN
                RAISE EXCEPTION 'only read_at of a paper alert may change, once' USING ERRCODE = '{SQLSTATE}';
            END IF;
            RETURN NEW;
        END
        $fn$
        """


TRIGGERS_PIN = _M4._md5_body(_triggers_guard_sql())
ALERTS_PIN = _M4._md5_body(_alerts_guard_sql())


def _block() -> str:
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (GC-TP 7a): paper_triggers and paper_alerts: SELECT, column-limited INSERT and UPDATE
    --    exactly as granted, no DELETE / TRUNCATE; the guards enabled with their pinned bodies
    IF phase = 'post' THEN
{_M16._table_block(TRIGGERS, "paper_triggers", TRIGGER_INSERT_COLUMNS, TRIGGER_UPDATE_COLUMNS, TRIGGERS_GUARD,
                   TRIGGERS_TRIGGER, TRIGGERS_PIN)}
{_M16._table_block(ALERTS, "paper_alerts", ALERT_INSERT_COLUMNS, ALERT_UPDATE_COLUMNS, ALERTS_GUARD, ALERTS_TRIGGER,
                   ALERTS_PIN)}
{_M16._M3._sequence_checks(TRIGGERS_SEQUENCE, "paper trigger id", usage=True)}
{_M16._M3._sequence_checks(ALERTS_SEQUENCE, "paper alert id", usage=True)}
    END IF;
"""


def previous_allowlist_sql() -> str:
    return _PREVIOUS.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """The predecessor's chain text plus block 22. Fails closed (RuntimeError) on a changed shape or a block 22 in."""
    previous = previous_allowlist_sql()
    if previous.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous or "-- 22." in previous:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the paper trigger checks safely")
    return previous.replace(_INSERT_BEFORE, _block() + _INSERT_BEFORE, 1)


def _grant(role: str, table: str, sequence: str, guard: str,  # noqa: PLR0913 - one grant set per table
           inserts: tuple[str, ...], updates: tuple[str, ...]) -> None:
    op.execute(f"REVOKE ALL ON FUNCTION {guard}() FROM PUBLIC")
    op.execute(f'REVOKE ALL ON FUNCTION {guard}() FROM "{role}"')
    op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
    op.execute(f'REVOKE ALL ON TABLE {table} FROM "{role}"')
    op.execute(f'GRANT SELECT ON TABLE {table} TO "{role}"')
    op.execute(f'GRANT INSERT ({", ".join(inserts)}) ON TABLE {table} TO "{role}"')
    op.execute(f'GRANT UPDATE ({", ".join(updates)}) ON TABLE {table} TO "{role}"')
    op.execute(f"REVOKE ALL ON SEQUENCE {sequence} FROM PUBLIC")
    op.execute(f'REVOKE ALL ON SEQUENCE {sequence} FROM "{role}"')
    op.execute(f'GRANT USAGE ON SEQUENCE {sequence} TO "{role}"')


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    kinds = ", ".join(f"'{k}'" for k in KINDS)
    directions = ", ".join(f"'{d}'" for d in DIRECTIONS)
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(
        f"""
        CREATE TABLE {TRIGGERS} (
            id           BIGSERIAL     PRIMARY KEY,
            strategy_id  BIGINT        NOT NULL REFERENCES public.strategies (id),
            kind         TEXT          NOT NULL CHECK (kind IN ({kinds})),
            contract_id  BIGINT        NULL REFERENCES public.catalogue_contracts (id),
            underlying   TEXT          NULL,
            direction    TEXT          NOT NULL CHECK (direction IN ({directions})),
            level        NUMERIC(14,2) NOT NULL CHECK (level > 0),
            created_at   TIMESTAMPTZ   NOT NULL DEFAULT clock_timestamp(),
            fired_at     TIMESTAMPTZ   NULL,
            cancelled_at TIMESTAMPTZ   NULL,
            CHECK ((kind = 'leg_stop') = (contract_id IS NOT NULL)),
            CHECK ((kind = 'conditional_exit') = (underlying IS NOT NULL)),
            CHECK (fired_at IS NULL OR cancelled_at IS NULL)
        )
        """
    )
    op.execute(f"CREATE INDEX paper_triggers_armed ON {TRIGGERS} (strategy_id) "
               "WHERE fired_at IS NULL AND cancelled_at IS NULL")
    op.execute(
        f"""
        CREATE TABLE {ALERTS} (
            id          BIGSERIAL   PRIMARY KEY,
            strategy_id BIGINT      NOT NULL REFERENCES public.strategies (id),
            trigger_id  BIGINT      NOT NULL REFERENCES {TRIGGERS} (id),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            title       TEXT        NOT NULL,
            body        TEXT        NOT NULL,
            read_at     TIMESTAMPTZ NULL
        )
        """
    )
    op.execute(f"CREATE UNIQUE INDEX paper_alerts_trigger ON {ALERTS} (trigger_id)")  # one alert per fire
    op.execute(f"CREATE INDEX paper_alerts_strategy ON {ALERTS} (strategy_id, id)")
    for guard_sql, trigger, table, guard in ((_triggers_guard_sql(), TRIGGERS_TRIGGER, TRIGGERS, TRIGGERS_GUARD),
                                             (_alerts_guard_sql(), ALERTS_TRIGGER, ALERTS, ALERTS_GUARD)):
        op.execute(guard_sql)
        op.execute(f"CREATE TRIGGER {trigger} BEFORE INSERT OR UPDATE OR DELETE ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION {guard}()")
    _grant(role, TRIGGERS, TRIGGERS_SEQUENCE, TRIGGERS_GUARD, TRIGGER_INSERT_COLUMNS, TRIGGER_UPDATE_COLUMNS)
    _grant(role, ALERTS, ALERTS_SEQUENCE, ALERTS_GUARD, ALERT_INSERT_COLUMNS, ALERT_UPDATE_COLUMNS)
    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    role = _BASE._app_role()
    op.execute(previous_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {_BASE.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"DROP TABLE {ALERTS}")
    op.execute(f"DROP TABLE {TRIGGERS}")
    op.execute(f"DROP FUNCTION {ALERTS_GUARD}()")
    op.execute(f"DROP FUNCTION {TRIGGERS_GUARD}()")
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
