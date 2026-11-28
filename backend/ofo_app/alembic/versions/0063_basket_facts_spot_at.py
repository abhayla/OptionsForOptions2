"""Each basket's facts keep the time of the spot quote they used (Lane RA2 item 6; ADR-283 (1), ADR-048, ADR-008).

Spec basis: ADR-283 (1) (the starting point of every playbook rule is the market state at the basket's fill: order
clock, spot, ATM IV and every open leg's price); FR 3.4 (Lane FD5: ``BasketFacts.spot_at`` is the time of the quote the
spot came from, which differs from the order clock when the user confirmed a not-live index value); ADR-048 (the
application role); ADR-008 (a time, no money).

Why: ``spot_at`` was carried to the writer and dropped there (Lane FD5 "Not done"): a stored basket fact could say
"spot 24187.35" but not when that spot was seen.

Changes (owner-run, one transaction; ADDITIVE): public.strategy_basket_facts gains ``spot_at TIMESTAMPTZ NULL`` (no
default, no back-fill: a basket stored before this has no time and reads NULL), and the application role may INSERT it
(column grant, like the six columns of 0050). The insert-only guard (OF050) is unchanged. The app-role allow-list
function pins the INSERT columns of this table exactly (0050's block 34), so its chain text moves from six to seven
columns in the same migration (0060's chain text is the previous one: 0061 and 0062 left it alone); it fails closed
(RuntimeError) when the old column check is not in the chain exactly once.

Old-code compatibility: old code inserts the six columns it always did, so it keeps working on a migrated database (the
new column is nullable); new code on an un-migrated database logs "basket facts not stored" in its own savepoint and
never fails the fill (``entry_facts_store.record_basket``). Deploy order: migrate first or last.
Downgrade drops the column: the stored times are lost, nothing else.

Revision ID: 0063_basket_facts_spot_at
Revises: 0062_order_request_keys_expiry
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0063_basket_facts_spot_at"
down_revision = "0062_order_request_keys_expiry"
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


_M50 = _load("0050_strategy_basket_facts.py", "ofo_migration_0050_for_0063")
_M60 = _load("0060_plan_stamp_only_on_switch.py", "ofo_migration_0060_for_0063")  # the newest holder of the chain text
_BASE = _M50._BASE

TABLE = _M50.TABLE
NEW_COLUMNS = (*_M50.INSERT_COLUMNS, "spot_at")


def _insert_check(columns: tuple[str, ...]) -> str:
    return _M50._M16._M3._columns_exactly(TABLE, _M50.LABEL, "INSERT", columns)


def previous_allowlist_sql() -> str:
    return _M60.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """The chain text with block 34's INSERT column check naming the seventh column. Fails closed on a changed shape."""
    previous = previous_allowlist_sql()
    old, new = _insert_check(_M50.INSERT_COLUMNS), _insert_check(NEW_COLUMNS)
    if previous.count(old) != 1 or new in previous:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the spot_at column check safely")
    return previous.replace(old, new, 1)


def _install(allowlist_sql: str) -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(allowlist_sql)
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def upgrade() -> None:
    role = _BASE._app_role()
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'pre')")
    op.execute(f"ALTER TABLE {TABLE} ADD COLUMN spot_at TIMESTAMPTZ")
    op.execute(f'GRANT INSERT (spot_at) ON TABLE {TABLE} TO "{role}"')
    _install(extended_allowlist_sql())


def downgrade() -> None:
    op.execute(f"ALTER TABLE {TABLE} DROP COLUMN spot_at")  # the column grant goes with the column
    _install(previous_allowlist_sql())
