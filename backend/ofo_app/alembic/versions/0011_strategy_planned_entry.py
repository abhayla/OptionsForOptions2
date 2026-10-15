"""Strategy store: a leg keeps its planned entry price and capture time (issue #208, ADR-075).

Spec basis: REQ-038 AC-5 ("Each leg's planned entry price and its capture time are part of the definition and are
saved with it (ADR-075)."); ADR-075 ("LTP, bid, ask, IV and health stay out of the stored strategy (ADR-062 unchanged
for live prices).").

Copy from: none - this re-creates migration 0010's own validators.

The stored leg is a JSONB object inside ``definition`` (0008), so the two values are typed slots of that object, not
table columns: ``planned_entry`` is a JSON string that is a positive NUMERIC(14,2) value written as plain digits (the
Decimal's exact text; a JSON number is refused), ``captured_at`` is a JSON string that casts to TIMESTAMPTZ and carries
its UTC offset (Python's ``isoformat`` of an aware datetime). The guard (0008, SECURITY DEFINER) calls the positive
validator on every insert and update, and a refusal is SQLSTATE 23514 (check_violation), so it acts as the CHECK.

Changes (owner-run, one transaction):
- public.ofo_strategy_leg_valid: the key set of a definition leg is an ALLOW-LIST of exactly two shapes - the six 0008
  keys, or those six plus both ``planned_entry`` and ``captured_at`` (eight keys). Anything else (one of the pair alone,
  an ``ltp`` next to the pair, any other extra key) is refused. A change-item leg (without contract id) is unchanged:
  exactly its five keys.
- public.ofo_strategy_change_items_valid: one new item kind ``entries_repriced`` (exactly the key ``kind``), the summary
  of a reprice (ADR-068 item 1: the planned entry changes only when the user asks to reprice).
- public.ofo_assert_app_role_allowlist: 0010's text with block 11's md5 pins of the two changed validators replaced.
- downgrade: refuses while any stored definition (current or history) holds a planned entry - 0010's validators and
  0010's domain would refuse to load such a row (history is append-only, so it cannot be stripped); otherwise 0010's
  validators and allowlist come back.

Revision ID: 0011_strategy_planned_entry
Revises: 0010_strategy_schema_version
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0011_strategy_planned_entry"
down_revision = "0010_strategy_schema_version"
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


_M10 = _load("0010_strategy_schema_version.py", "ofo_migration_0010_for_0011")
_M8 = _M10._M8
_M4 = _M8._M4
_BASE = _M8._BASE  # 0001

#: ofo.strategy.stored_form ENTRY_LEG_KEYS / ENTRY_PRICE_PATTERN / CAPTURED_AT_PATTERN (a migration never imports
#: application code; tests/strategy/test_stored_form_entries.py pins these equal to the domain's).
ENTRY_LEG_KEYS = ("planned_entry", "captured_at")
ENTRY_PRICE_REGEX = "^(0|[1-9][0-9]{0,11})([.][0-9]{1,2})?$"
CAPTURED_AT_REGEX = "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}([.](?!000000)[0-9]{6})?[+-][0-9]{2}:[0-9]{2}$"
ENTRIES_REPRICED = "entries_repriced"

_PAIR = "ARRAY['planned_entry', 'captured_at']"
_OLD_KEY_COUNT = "IS DISTINCT FROM (CASE WHEN with_id THEN 6 ELSE 5 END)"
_NEW_KEY_COUNT = (f"IS DISTINCT FROM (CASE WHEN NOT with_id THEN 5 "
                  f"WHEN coalesce(leg ?| {_PAIR}, FALSE) THEN 8 ELSE 6 END)")
_OLD_LEG_END = """            RETURN TRUE;
        EXCEPTION WHEN others THEN"""
# Escaped braces: the validator text is built with f-strings in 0008; here plain strings, so single braces.
_NEW_LEG_END = f"""            IF with_id AND coalesce(leg ?| {_PAIR}, FALSE) THEN
                IF NOT coalesce(leg ?& {_PAIR}, FALSE) THEN
                    RETURN FALSE;
                END IF;
                IF NOT coalesce(jsonb_typeof(leg -> 'planned_entry') = 'string'
                                AND (leg ->> 'planned_entry') ~ '{ENTRY_PRICE_REGEX}'
                                AND (leg ->> 'planned_entry')::numeric(14,2) > 0, FALSE) THEN
                    RETURN FALSE;
                END IF;
                IF NOT coalesce(jsonb_typeof(leg -> 'captured_at') = 'string'
                                AND (leg ->> 'captured_at') ~ '{CAPTURED_AT_REGEX}'
                                AND (leg ->> 'captured_at')::timestamptz IS NOT NULL, FALSE) THEN
                    RETURN FALSE;
                END IF;
            END IF;
{_OLD_LEG_END}"""
_OLD_SIMPLE_KINDS = "ELSIF kind IN ('legs_reordered', 'replaced_unreadable') THEN"
_NEW_SIMPLE_KINDS = f"ELSIF kind IN ('legs_reordered', 'replaced_unreadable', '{ENTRIES_REPRICED}') THEN"

LEG_SIGNATURE = f"{_M8.LEG_VALIDATOR}(jsonb,boolean)"
ITEMS_SIGNATURE = f"{_M8.ITEMS_VALIDATOR}(jsonb)"


def _replaced_once(sql: str, old: str, new: str) -> str:
    if sql.count(old) != 1:
        raise RuntimeError(f"migration 0010's validator text changed shape: {old!r} found {sql.count(old)} times")
    return sql.replace(old, new, 1)


def _old_validators() -> dict[str, str]:
    """0010's validators (CREATE OR REPLACE): the downgrade."""
    return _M10._new_validators()


def _new_validators() -> dict[str, str]:
    out = {}
    for signature, sql in _old_validators().items():
        if signature == LEG_SIGNATURE:
            sql = _replaced_once(_replaced_once(sql, _OLD_KEY_COUNT, _NEW_KEY_COUNT), _OLD_LEG_END, _NEW_LEG_END)
        elif signature == ITEMS_SIGNATURE:
            sql = _replaced_once(sql, _OLD_SIMPLE_KINDS, _NEW_SIMPLE_KINDS)
        out[signature] = sql
    return out


NEW_PINS = {signature: _M4._md5_body(sql) for signature, sql in _new_validators().items()}


def extended_allowlist_sql() -> str:
    """0010's allowlist text with block 11's pins of the validators whose body changed replaced by the new ones."""
    sql = _M10.extended_allowlist_sql()
    for signature, old_pin in _M10.NEW_PINS.items():
        new_pin = NEW_PINS[signature]
        if new_pin != old_pin:
            sql = _replaced_once(sql, f"'{old_pin}'", f"'{new_pin}'")
    return sql


def previous_allowlist_sql() -> str:
    return _M10.extended_allowlist_sql()


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
    # A planned entry is the user's data, and history is append-only: refuse rather than strip or strand it.
    op.execute(
        f"""
        DO $down$
        DECLARE
            has_entries BOOLEAN := FALSE;
        BEGIN
            EXECUTE 'LOCK TABLE {_M8.STRATEGIES}, {_M8.HISTORY} IN ACCESS EXCLUSIVE MODE';
            EXECUTE 'SELECT EXISTS (SELECT 1 FROM {_M8.STRATEGIES} s, jsonb_array_elements(s.definition -> ''legs'') l
                                    WHERE l ? ''planned_entry'' OR l ? ''captured_at'')
                     OR EXISTS (SELECT 1 FROM {_M8.HISTORY} h, jsonb_array_elements(h.definition -> ''legs'') l
                                WHERE l ? ''planned_entry'' OR l ? ''captured_at'')' INTO has_entries;
            IF has_entries THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: a stored strategy holds a planned entry';
            END IF;
        END
        $down$;
        """
    )
    _install(_old_validators(), previous_allowlist_sql())
