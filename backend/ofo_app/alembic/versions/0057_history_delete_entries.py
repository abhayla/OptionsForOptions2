"""Strategy history: a delete and its Undo leave an entry each, kinds ``deleted`` and ``undeleted`` (ADR-330 (31)).

Spec basis: ADR-330 (31) ("A delete and its Undo are recorded in the strategy's history as "Deleted" and "Restored"
entries with their times"); ADR-292 (delete / undelete); REQ-070 AC-6 / AC-8; ADR-048 (the limited application role).

Copy from: 0011 (``entries_repriced``: one new simple item kind, ``_NEW_SIMPLE_KINDS``) and 0025 (the validator
re-created from the previous text, the allow-list pin swapped), 0056 (the allow-list chain).

Changes (owner-run, one transaction):
- public.ofo_strategy_change_items_valid: 0025's body with two new item kinds, ``deleted`` and ``undeleted``, each
  exactly the key ``kind`` (like ``legs_reordered``). Every other shape is still refused with SQLSTATE 23514.
  No table, column or grant changes: the application role already inserts into strategy_history.
- public.ofo_assert_app_role_allowlist: 0056's chain text with the items-validator pin replaced.
- downgrade: refuses (SQLSTATE of 0039) while any history entry holds a ``deleted`` or ``undeleted`` item (history is
  append-only and a user's record must not vanish silently); otherwise 0025's validator and 0056's allow-list return.

Old-code compatibility: additive. Code before this migration never writes the two kinds; when it READS a history that
holds one, ``render_summary`` shows the fixed line "this change could not be shown" (an unknown kind is never shown
raw) and the entry is offered Restore, which is harmless: the entry holds the definition that was current at that time
and restoring a definition equal to the current one writes nothing.

Revision ID: 0057_history_delete_entries
Revises: 0056_several_standard_playbooks
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0057_history_delete_entries"
down_revision = "0056_several_standard_playbooks"
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


_M25 = _load("0025_strategy_name.py", "ofo_migration_0025_for_0057")
_M39 = _load("0039_strategy_entry_facts.py", "ofo_migration_0039_for_0057")
_M56 = _load(f"{down_revision}.py", "ofo_migration_0056_for_0057")
_M8 = _M25._M8
_M4 = _M25._M4
_BASE = _M25._BASE
ITEMS_SIGNATURE = _M25.ITEMS_SIGNATURE
SQLSTATE = _M39.SQLSTATE
DELETED = "deleted"
UNDELETED = "undeleted"

_OLD_SIMPLE_KINDS = "ELSIF kind IN ('legs_reordered', 'replaced_unreadable', 'entries_repriced') THEN"
_NEW_SIMPLE_KINDS = ("ELSIF kind IN ('legs_reordered', 'replaced_unreadable', 'entries_repriced', "
                     f"'{DELETED}', '{UNDELETED}') THEN")


def _replaced_once(sql: str, old: str, new: str) -> str:
    if sql.count(old) != 1:
        raise RuntimeError(f"the previous migration's text changed shape: {old[:70]!r} found {sql.count(old)} times")
    return sql.replace(old, new, 1)


def _old_items_sql() -> str:
    return _M25._new_items_sql()


def _new_items_sql() -> str:
    return _replaced_once(_old_items_sql(), _OLD_SIMPLE_KINDS, _NEW_SIMPLE_KINDS)


OLD_ITEMS_PIN = _M25.NEW_ITEMS_PIN
NEW_ITEMS_PIN = _M4._md5_body(_new_items_sql())
NEW_PINS = {ITEMS_SIGNATURE: NEW_ITEMS_PIN}


def previous_allowlist_sql() -> str:
    return _M56.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """0056's chain text with the items-validator pin replaced. Fails closed on a changed shape."""
    return _replaced_once(previous_allowlist_sql(), f"'{OLD_ITEMS_PIN}'", f"'{NEW_ITEMS_PIN}'")


def _install(items_sql: str, allowlist_sql: str) -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(items_sql)
    op.execute(allowlist_sql)
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def upgrade() -> None:
    role = _BASE._app_role()
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'pre')")
    _install(_new_items_sql(), extended_allowlist_sql())


def downgrade() -> None:
    # History is append-only and a delete record is the user's own trail: refuse rather than strip or strand it.
    op.execute(
        f"""
        DO $down$
        DECLARE
            n BIGINT;
        BEGIN
            EXECUTE 'LOCK TABLE {_M8.HISTORY} IN ACCESS EXCLUSIVE MODE';
            EXECUTE 'SELECT count(*) FROM {_M8.HISTORY} h WHERE EXISTS (
                         SELECT 1 FROM jsonb_array_elements(h.change_summary) i
                         WHERE i ->> ''kind'' IN (''{DELETED}'', ''{UNDELETED}''))' INTO n;
            IF n > 0 THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: {_M8.HISTORY} holds % delete or restore entries', n
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
        END
        $down$;
        """  # noqa: S608 - constant names only
    )
    _install(_old_items_sql(), previous_allowlist_sql())
