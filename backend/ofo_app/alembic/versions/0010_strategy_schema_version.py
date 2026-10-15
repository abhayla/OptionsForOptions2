"""Strategy store: only a schema version the domain can load is storable; validators are STABLE, not IMMUTABLE (W-061
follow-ups, issues #138 and #167).

Spec basis: REQ-038 AC-5 ("A strategy's definition and its activity history are saved in the database when the user
presses Save Draft, survive a restart, and load back exactly as saved; live prices are never saved inside the
strategy."): a definition the database stores but the domain refuses to load (``schema_version_unknown``) does not
"load back exactly as saved".

Copy from: none - this re-creates migration 0008's own validators.

Changes (owner-run, one transaction):
- public.ofo_strategy_definition_valid: ``schema_version`` must be one of SUPPORTED_SCHEMA_VERSIONS (today 1 -
  ofo.strategy.stored_form.SUPPORTED_SCHEMA_VERSIONS; copied here on purpose, pinned equal by
  tests/strategy/test_bounds.py), not any positive integer. The CHECK on both tables (the document's schema_version
  equals the column) is unchanged, so version 2 cannot be stored with either value.
- public.ofo_strategy_leg_valid / ofo_strategy_definition_valid / ofo_strategy_change_items_valid are marked STABLE
  instead of IMMUTABLE: they cast text to ``date`` (a DateStyle-dependent cast is not immutable). Harmless before (no
  index or CHECK uses them); true now. Ownership, grants (no EXECUTE for the application role) and the search_path pin
  are kept (CREATE OR REPLACE).
- public.ofo_assert_app_role_allowlist: 0009's text with block 11's md5 pin of the definition validator bumped.
  Fails closed (RuntimeError) if 0008's or 0009's text changed shape.
- downgrade: 0008's validators and 0009's allowlist text come back. No rows are refused: the downgrade only loosens.

Revision ID: 0010_strategy_schema_version
Revises: 0009_minute_history
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0010_strategy_schema_version"
down_revision = "0009_minute_history"
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


_M9 = _load("0009_minute_history.py", "ofo_migration_0009_for_0010")
_M8 = _M9._M8
_M4 = _M8._M4
_BASE = _M8._BASE  # 0001

#: ofo.strategy.stored_form.SUPPORTED_SCHEMA_VERSIONS (a migration never imports application code).
SUPPORTED_SCHEMA_VERSIONS = (1,)

_OLD_VERSION_TEST = "AND (d ->> 'schema_version') ~ '^[1-9][0-9]{0,8}$'"
_NEW_VERSION_TEST = "AND (d ->> 'schema_version') IN (" + ", ".join(f"'{v}'" for v in SUPPORTED_SCHEMA_VERSIONS) + ")"


def _replaced_once(sql: str, old: str, new: str) -> str:
    if sql.count(old) != 1:
        raise RuntimeError(f"migration 0008's validator text changed shape: {old!r} found {sql.count(old)} times")
    return sql.replace(old, new, 1)


def _as_replace(sql: str) -> str:
    return _replaced_once(sql, "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION")


def _old_validators() -> dict[str, str]:
    """0008's validators as CREATE OR REPLACE statements (the downgrade)."""
    return {signature: _as_replace(sql) for signature, sql in _M8.VALIDATOR_SQL.items()}


def _new_validators() -> dict[str, str]:
    out = {}
    for signature, sql in _M8.VALIDATOR_SQL.items():
        sql = _replaced_once(_as_replace(sql), "LANGUAGE plpgsql IMMUTABLE", "LANGUAGE plpgsql STABLE")
        if signature == f"{_M8.DEFINITION_VALIDATOR}(jsonb)":
            sql = _replaced_once(sql, _OLD_VERSION_TEST, _NEW_VERSION_TEST)
        out[signature] = sql
    return out


NEW_PINS = {signature: _M4._md5_body(sql) for signature, sql in _new_validators().items()}


def extended_allowlist_sql() -> str:
    """0009's allowlist text with block 11's pins of the validators whose body changed replaced by the new ones."""
    sql = _M9.extended_allowlist_sql()
    for signature, old_pin in _M8.VALIDATOR_PINS.items():
        new_pin = NEW_PINS[signature]
        if new_pin != old_pin:
            sql = _replaced_once(sql, f"'{old_pin}'", f"'{new_pin}'")
    return sql


def previous_allowlist_sql() -> str:
    return _M9.extended_allowlist_sql()


def _install(validators: dict[str, str], allowlist_sql: str) -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    for sql in validators.values():
        op.execute(sql)
    op.execute(allowlist_sql)
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def upgrade() -> None:
    role = _BASE._app_role()
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'pre')")
    _install(_new_validators(), extended_allowlist_sql())


def downgrade() -> None:
    _install(_old_validators(), previous_allowlist_sql())
