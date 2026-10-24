"""Strategy store: the name a user gives a saved strategy, stored beside the definition (REQ-134, W-157).

Spec basis: REQ-134 AC-1 ("1 to 40 characters after trimming spaces"; "Two strategies of one user may share a name");
AC-3 ("Renaming changes only the name; it adds a history entry ... and never changes legs, prices, tracking state or
version"); ADR-048 (the limited application role); ADR-003 (the user's own text is only quoted, in a labelled field).

Copy from: none - this repo's own pattern: 0011's validator replacement (CREATE OR REPLACE of the same function, the
allow-list pins swapped), 0008's guard and table block, 0024's downgrade refusal.

Changes (owner-run, one transaction):
- public.strategies.name TEXT NOT NULL DEFAULT 'New Strategy' (rows saved before this migration get the default; no data
  repair) with CHECK: 1..40 characters after btrim, no control character. Not unique (duplicates are allowed).
- Grants: the application role gets column INSERT and column UPDATE on ``name`` (and nothing else new).
- Guard public.strategies_guard: 0008's text with ONE change - an UPDATE that leaves the definition as it is keeps
  ``updated_at`` (the last-saved time follows the definition, not a rename) and, as before, bumps no ``revision``.
  Every other column in FIXED_COLUMNS (id, user_ref, underlying, status, created_at, definition_schema_version,
  revision) is still refused; a name change needs no history entry from the guard (the store writes one).
- public.ofo_strategy_change_items_valid: 0011's body with one new item kind ``renamed`` = exactly the keys kind, from,
  to; each a string, trimmed, 1..40 characters, no control character (the user's own words, REQ-134 AC-3).
- public.ofo_assert_app_role_allowlist: 0024's chain text with block 11's strategies block (INSERT/UPDATE column lists,
  guard pin) and the items-validator pin replaced.
- downgrade: refuses while any strategy has a name other than the default or any history entry holds a ``renamed``
  item (a user's own words must not vanish silently); otherwise 0024's state comes back.

Revision ID: 0025_strategy_name
Revises: 0024_typed_entry_mark
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0025_strategy_name"
down_revision = "0024_typed_entry_mark"
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


_PREVIOUS = _load(f"{down_revision}.py", "ofo_migration_predecessor_for_0025")  # 0024
_M11 = _PREVIOUS._M11
_M8 = _PREVIOUS._M8
_M4 = _PREVIOUS._M4
_BASE = _PREVIOUS._BASE  # 0001

#: Copied on purpose (a migration never imports application code); tests pin them equal to ofo.strategy.stored_form's.
NAME_MAX = 40
DEFAULT_NAME = "New Strategy"
#: C0 controls (except none), DEL and C1 controls: a name is one line of printable text.
CONTROL_REGEX = r"[\x01-\x1f\x7f-\x9f]"
NAME_COLUMN = "name"
NAME_CONSTRAINT = "strategies_name_shape"

INSERT_COLUMNS = (*_M8.STRATEGIES_INSERT_COLUMNS, NAME_COLUMN)
UPDATE_COLUMNS = (*_M8.STRATEGIES_UPDATE_COLUMNS, NAME_COLUMN)
RENAMED = "renamed"
ITEMS_SIGNATURE = _M11.ITEMS_SIGNATURE


def _replaced_once(sql: str, old: str, new: str) -> str:
    if sql.count(old) != 1:
        raise RuntimeError(f"the previous migration's text changed shape: {old[:60]!r} found {sql.count(old)} times")
    return sql.replace(old, new, 1)


def _name_ok(expr: str) -> str:
    return (f"(jsonb_typeof({expr}) = 'string' AND char_length({expr} #>> '{{}}') BETWEEN 1 AND {NAME_MAX} "
            f"AND btrim({expr} #>> '{{}}') = ({expr} #>> '{{}}') AND ({expr} #>> '{{}}') !~ '{CONTROL_REGEX}')")


# --- the guard -------------------------------------------------------------------------------------------------------

_OLD_GUARD_END = """            NEW.updated_at := clock_timestamp();
            RETURN NEW;
        END
        $fn$"""
_NEW_GUARD_END = """            IF NEW.definition IS DISTINCT FROM OLD.definition THEN
                NEW.updated_at := clock_timestamp();
            ELSE
                NEW.updated_at := OLD.updated_at;  -- REQ-134 AC-3: a rename is not a save of the definition
            END IF;
            RETURN NEW;
        END
        $fn$"""


def _old_guard_sql() -> str:
    return _M8._strategies_guard_sql()


def _new_guard_sql() -> str:
    return _replaced_once(_old_guard_sql(), _OLD_GUARD_END, _NEW_GUARD_END)


# --- the change-item validator ---------------------------------------------------------------------------------------

_OLD_RESTORED = "ELSIF kind = 'restored' THEN"


def _old_items_sql() -> str:
    return _M11._new_validators()[ITEMS_SIGNATURE]


def _new_items_sql() -> str:
    from_ok, to_ok = _name_ok("(item -> 'from')"), _name_ok("(item -> 'to')")
    branch = (f"ELSIF kind = '{RENAMED}' THEN\n"
              f"                    ok := slots = 3 AND item ?& ARRAY['from', 'to'] AND {from_ok} AND {to_ok};\n"
              f"                ")
    return _replaced_once(_old_items_sql(), _OLD_RESTORED, branch + _OLD_RESTORED)


OLD_GUARD_PIN = _M8.STRATEGIES_PINNED_BODY
NEW_GUARD_PIN = _M4._md5_body(_new_guard_sql())
OLD_ITEMS_PIN = _M11.NEW_PINS[ITEMS_SIGNATURE]
NEW_ITEMS_PIN = _M4._md5_body(_new_items_sql())


def _strategies_block(insert_columns, update_columns, pin: str) -> str:
    return _M8._table_block(_M8.STRATEGIES, "strategies", insert_columns, update_columns, _M8.STRATEGIES_SEQUENCE,
                            _M8.STRATEGIES_GUARD, _M8.STRATEGIES_TRIGGER, pin)


def previous_allowlist_sql() -> str:
    return _PREVIOUS.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """0024's chain text with block 11's strategies block and the items-validator pin replaced. Fails closed."""
    sql = _replaced_once(previous_allowlist_sql(),
                         _strategies_block(_M8.STRATEGIES_INSERT_COLUMNS, _M8.STRATEGIES_UPDATE_COLUMNS, OLD_GUARD_PIN),
                         _strategies_block(INSERT_COLUMNS, UPDATE_COLUMNS, NEW_GUARD_PIN))
    return _replaced_once(sql, f"'{OLD_ITEMS_PIN}'", f"'{NEW_ITEMS_PIN}'")


def _install(guard_sql: str, items_sql: str, allowlist_sql: str) -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(guard_sql)
    op.execute(items_sql)
    op.execute(allowlist_sql)
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def upgrade() -> None:
    role = _BASE._app_role()
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'pre')")
    op.execute(f"ALTER TABLE {_M8.STRATEGIES} ADD COLUMN {NAME_COLUMN} TEXT NOT NULL DEFAULT '{DEFAULT_NAME}'")
    op.execute(f"ALTER TABLE {_M8.STRATEGIES} ADD CONSTRAINT {NAME_CONSTRAINT} CHECK ("
               f"char_length(btrim({NAME_COLUMN})) BETWEEN 1 AND {NAME_MAX} AND char_length({NAME_COLUMN}) <= {NAME_MAX} "
               f"AND {NAME_COLUMN} !~ '{CONTROL_REGEX}')")
    op.execute(f'GRANT INSERT ({NAME_COLUMN}) ON TABLE {_M8.STRATEGIES} TO "{role}"')
    op.execute(f'GRANT UPDATE ({NAME_COLUMN}) ON TABLE {_M8.STRATEGIES} TO "{role}"')
    _install(_new_guard_sql(), _new_items_sql(), extended_allowlist_sql())


def downgrade() -> None:
    # A name or a rename entry is the user's own words and history is append-only: refuse rather than strip them.
    op.execute(
        f"""
        DO $down$
        DECLARE
            has_names BOOLEAN := FALSE;
        BEGIN
            EXECUTE 'LOCK TABLE {_M8.STRATEGIES}, {_M8.HISTORY} IN ACCESS EXCLUSIVE MODE';
            EXECUTE 'SELECT EXISTS (SELECT 1 FROM {_M8.STRATEGIES} WHERE {NAME_COLUMN} <> ''{DEFAULT_NAME}'')' INTO has_names;
            IF has_names THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: a strategy in {_M8.STRATEGIES} has a name the user chose';
            END IF;
            EXECUTE 'SELECT EXISTS (SELECT 1 FROM {_M8.HISTORY} h, jsonb_array_elements(h.change_summary) i
                                    WHERE i ->> ''kind'' = ''{RENAMED}'')' INTO has_names;
            IF has_names THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: {_M8.HISTORY} holds a rename entry';
            END IF;
        END
        $down$;
        """
    )
    op.execute(f"ALTER TABLE {_M8.STRATEGIES} DROP CONSTRAINT {NAME_CONSTRAINT}")
    op.execute(f"ALTER TABLE {_M8.STRATEGIES} DROP COLUMN {NAME_COLUMN}")  # its column grants go with it
    _install(_old_guard_sql(), _old_items_sql(), previous_allowlist_sql())
