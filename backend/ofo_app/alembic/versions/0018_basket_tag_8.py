"""Execution plan orders: accept the 8-character basket tag bound to its row (GC-3L fix, 2026-10-19).

Basis: REQ-073 AC-2 (every order carries our own tag identifying strategy, plan version and leg, at most 8 characters,
Kite Publisher's basket limit); finding basket-tag-exceeds-publisher-limit (Kite's basket answered "`tag` should be max
8 characters" for strategy 11 plan 1 tag ``OFS11V1L0`` on 2026-10-19 10:19:48 IST; nothing was placed); ADR-048 (this
revision runs as the owner role; the application role's grants are unchanged - no new function, no new column).

The tag grammar lives in ``ofo.execution.basket.make_tag``: ``Q`` + strategy id (4 base-36 digits) + plan number (2) +
leg index (1), zero-padded, digits then uppercase letters. Legacy rows keep ``OFS<strategy>V<plan>L<leg>`` (live in
Zerodha's book and in stored plans), so the row CHECK accepts EITHER grammar, each bound to the row's own
(strategy_id, plan_number, leg_index). The base-36 digits are computed inline in the CHECK (no SQL function, so the
application role's function allowlist chain is untouched).

upgrade: drops 0016's row CHECK (found by its definition, fails closed unless exactly one matches) and adds the named
CHECK ``execution_plan_orders_tag_of_row`` (legacy expression OR new expression within the ceilings).
downgrade: REAL while no new-grammar row exists (it would violate the old CHECK); refuses otherwise, in SQL.

Numbering: main's head is 0017_audit_order_prepared; held PR #419's migration is renumbered to 0019 after this merges.

Copy from: none - follows 0016's table and 0015's refusing-downgrade pattern.

Revision ID: 0018_basket_tag_8
Revises: 0017_audit_order_prepared
"""

from __future__ import annotations

from alembic import op
from ofo.execution.basket import (
    MAX_TAG_LEG_INDEX,
    MAX_TAG_PLAN_VERSION,
    MAX_TAG_STRATEGY_ID,
    TAG_DIGITS,
    TAG_LEG_WIDTH,
    TAG_PLAN_WIDTH,
    TAG_PREFIX,
    TAG_STRATEGY_WIDTH,
)

revision = "0018_basket_tag_8"
down_revision = "0017_audit_order_prepared"
branch_labels = None
depends_on = None

ORDERS = "public.execution_plan_orders"
TAG_CHECK = "execution_plan_orders_tag_of_row"
LEGACY_TAG_SQL = "tag = 'OFS' || strategy_id || 'V' || plan_number || 'L' || leg_index"


def _digit(expr: str, place: int) -> str:
    """The base-36 digit of ``expr`` at ``place`` (36**place), as uppercase text."""
    base = len(TAG_DIGITS)  # % before the cast: a BIGINT id above the ceiling never overflows, the BETWEEN refuses it
    return f"substr('{TAG_DIGITS}', ((({expr}) / {base ** place}) % {base})::integer + 1, 1)"


NEW_TAG_SQL = (
    f"strategy_id BETWEEN 1 AND {MAX_TAG_STRATEGY_ID} AND plan_number BETWEEN 1 AND {MAX_TAG_PLAN_VERSION}"
    f" AND leg_index BETWEEN 0 AND {MAX_TAG_LEG_INDEX} AND tag = '{TAG_PREFIX}'"
    + "".join(f" || {_digit('strategy_id', p)}" for p in reversed(range(TAG_STRATEGY_WIDTH)))
    + "".join(f" || {_digit('plan_number', p)}" for p in reversed(range(TAG_PLAN_WIDTH)))
    + "".join(f" || {_digit('leg_index', p)}" for p in reversed(range(TAG_LEG_WIDTH)))
)


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        DECLARE
            found TEXT[];
        BEGIN
            SELECT array_agg(conname) INTO found FROM pg_constraint
             WHERE conrelid = '{ORDERS}'::regclass AND contype = 'c'
               AND pg_get_constraintdef(oid) LIKE '%''OFS''%';
            IF coalesce(array_length(found, 1), 0) <> 1 THEN
                RAISE EXCEPTION 'expected exactly one legacy tag CHECK on {ORDERS}, found %', found;
            END IF;
            EXECUTE format('ALTER TABLE {ORDERS} DROP CONSTRAINT %I', found[1]);
        END
        $$
        """  # noqa: S608 constant table name
    )
    op.execute(f"ALTER TABLE {ORDERS} ADD CONSTRAINT {TAG_CHECK} CHECK (({LEGACY_TAG_SQL}) OR ({NEW_TAG_SQL}))")


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            EXECUTE 'LOCK TABLE {ORDERS} IN ACCESS EXCLUSIVE MODE';
            IF EXISTS (SELECT 1 FROM {ORDERS} WHERE tag LIKE 'Q%') THEN
                RAISE EXCEPTION 'refusing downgrade: {ORDERS} holds 8-character basket tags the legacy CHECK refuses';
            END IF;
        END
        $$
        """  # noqa: S608 constant table name
    )
    op.execute(f"ALTER TABLE {ORDERS} DROP CONSTRAINT {TAG_CHECK}")
    op.execute(f"ALTER TABLE {ORDERS} ADD CHECK ({LEGACY_TAG_SQL})")
