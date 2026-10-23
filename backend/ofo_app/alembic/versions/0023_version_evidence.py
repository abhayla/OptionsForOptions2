"""Version evidence: the plan's version link and the sticky reconciliation flag (W-144 fix round 1, REQ-038 AC-3/AC-4).

Basis: REQ-038 AC-3 ("A proposed version is separate from the active version"); REQ-038 AC-4 ("the broker's actual
state wins"); ADR-019 (versions after execution); ADR-018 / REQ-060 Q222 (an unresolved mismatch blocks; an agreeing
run does not unblock by itself); ADR-048 (the limited application role).

Copy from: none - modelled on 0022 (guard trigger, column grants, allow-list block swap read from the predecessor).

Changes (owner-run, one transaction):
- public.execution_plans.strategy_version: the version number the plan was built from (NULL = unknown: such a plan
  never activates a version). The application role may INSERT it (it is never updated).
- public.strategy_versions.reconciliation_required (default false): set on the ACTIVE version when an execution return
  leaves Zerodha away from it; while set, edits and confirmations are refused. The application role may UPDATE it.
- The 0022 guard also checks INSERT: a row is inserted 'proposed' (never confirmed or reconciled) or as version 1
  'active' with both stamps; never 'superseded', never another active number, never flagged. The flag changes only on
  the active row.
- public.ofo_assert_app_role_allowlist: the predecessor's chain text with the two table blocks swapped for the new
  column lists and the new guard pin (each found exactly once, else refused).
- downgrade: drops what upgrade adds and restores the 0022 guard body and chain text.

Revision ID: 0023_version_evidence
Revises: 0022_strategy_versions
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0023_version_evidence"
down_revision = "0022_strategy_versions"
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


_PREVIOUS = _load(f"{down_revision}.py", "ofo_migration_predecessor_for_0023")  # 0022
_M16 = _PREVIOUS._M16  # 0016: execution_plans and the table block helper
_BASE = _PREVIOUS._BASE  # 0001
_M4 = _PREVIOUS._M4  # 0004: _md5_body
_INSERT_BEFORE = _PREVIOUS._INSERT_BEFORE

SQLSTATE = _PREVIOUS.SQLSTATE
VERSIONS = _PREVIOUS.VERSIONS
GUARD = _PREVIOUS.GUARD
PLAN_LINK = "strategy_version"
FLAG = "reconciliation_required"
PLAN_INSERT_COLUMNS = (*_M16.PLAN_INSERT_COLUMNS, PLAN_LINK)
UPDATE_COLUMNS = (*_PREVIOUS.UPDATE_COLUMNS, FLAG)


def _guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {_PREVIOUS.SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.{FLAG} THEN
                    RAISE EXCEPTION 'a version is never inserted flagged' USING ERRCODE = '{SQLSTATE}';
                END IF;
                IF NEW.state = 'proposed' AND NEW.confirmed_at IS NULL AND NEW.reconciled_at IS NULL THEN
                    RETURN NEW;
                END IF;
                IF NEW.state = 'active' AND NEW.number = 1 AND NEW.based_on IS NULL
                   AND NEW.confirmed_at IS NOT NULL AND NEW.reconciled_at IS NOT NULL THEN
                    RETURN NEW;
                END IF;
                RAISE EXCEPTION 'a version is inserted proposed, or as version 1 active and reconciled'
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
            IF TG_OP <> 'UPDATE' THEN
                RAISE EXCEPTION 'strategy versions are never deleted' USING ERRCODE = '{SQLSTATE}';
            END IF;
            IF NEW.strategy_id IS DISTINCT FROM OLD.strategy_id OR NEW.number IS DISTINCT FROM OLD.number
               OR NEW.based_on IS DISTINCT FROM OLD.based_on OR NEW.created_at IS DISTINCT FROM OLD.created_at
               OR NEW.definition::text IS DISTINCT FROM OLD.definition::text
               OR NEW.definition_schema_version IS DISTINCT FROM OLD.definition_schema_version THEN
                RAISE EXCEPTION 'a strategy version is frozen' USING ERRCODE = '{SQLSTATE}';
            END IF;
            IF NEW.state IS DISTINCT FROM OLD.state AND NOT (
                   (OLD.state = 'proposed' AND NEW.state IN ('active', 'superseded'))
                OR (OLD.state = 'active' AND NEW.state = 'superseded')) THEN
                RAISE EXCEPTION 'version state % -> % is not allowed', OLD.state, NEW.state
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
            IF (OLD.confirmed_at IS NOT NULL AND NEW.confirmed_at IS DISTINCT FROM OLD.confirmed_at)
               OR (OLD.reconciled_at IS NOT NULL AND NEW.reconciled_at IS DISTINCT FROM OLD.reconciled_at) THEN
                RAISE EXCEPTION 'a version is confirmed and reconciled once' USING ERRCODE = '{SQLSTATE}';
            END IF;
            IF NEW.{FLAG} IS DISTINCT FROM OLD.{FLAG} AND OLD.state <> 'active' THEN
                RAISE EXCEPTION 'only the active version carries the reconciliation flag' USING ERRCODE = '{SQLSTATE}';
            END IF;
            RETURN NEW;
        END
        $fn$
        """


PIN = _M4._md5_body(_guard_sql())


def _plans_block(insert_cols) -> str:
    m = _M16
    return m._table_block(m.PLANS, "execution_plans", insert_cols, m.PLAN_UPDATE_COLUMNS, m.PLAN_GUARD,
                          m.PLAN_TRIGGER, m.PLAN_PIN)


def _versions_block(update_cols, pin: str) -> str:
    p = _PREVIOUS
    return _M16._table_block(VERSIONS, "strategy_versions", p.INSERT_COLUMNS, update_cols, GUARD, p.TRIGGER, pin)


def previous_allowlist_sql() -> str:
    return _PREVIOUS.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """0022's chain text with both table blocks swapped. Fails closed (RuntimeError) when either is not found once."""
    text = previous_allowlist_sql()
    for old, new in ((_plans_block(_M16.PLAN_INSERT_COLUMNS), _plans_block(PLAN_INSERT_COLUMNS)),
                     (_versions_block(_PREVIOUS.UPDATE_COLUMNS, _PREVIOUS.PIN), _versions_block(UPDATE_COLUMNS, PIN))):
        if text.count(old) != 1 or old == new:
            raise RuntimeError("previous allowlist SQL changed shape: cannot swap the version evidence blocks safely")
        text = text.replace(old, new, 1)
    return text


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(f"ALTER TABLE {_M16.PLANS} ADD COLUMN {PLAN_LINK} INTEGER "
               f"CHECK ({PLAN_LINK} IS NULL OR {PLAN_LINK} > 0)")
    op.execute(f"ALTER TABLE {VERSIONS} ADD COLUMN {FLAG} BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute(_guard_sql())
    op.execute(f'GRANT INSERT ({PLAN_LINK}) ON TABLE {_M16.PLANS} TO "{role}"')
    op.execute(f'GRANT UPDATE ({FLAG}) ON TABLE {VERSIONS} TO "{role}"')
    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f'REVOKE INSERT ({PLAN_LINK}) ON TABLE {_M16.PLANS} FROM "{role}"')
    op.execute(f'REVOKE UPDATE ({FLAG}) ON TABLE {VERSIONS} FROM "{role}"')
    op.execute(f"ALTER TABLE {_M16.PLANS} DROP COLUMN {PLAN_LINK}")
    op.execute(f"ALTER TABLE {VERSIONS} DROP COLUMN {FLAG}")
    op.execute(_PREVIOUS._guard_sql())
    op.execute(previous_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")
