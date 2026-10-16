"""Charge rates: tighter unit caps for SEBI and stamp duty (W-075; W-074 verifier MINOR D1).

Spec basis: ADR-082 ("The rates are admin settings with the date they were read"); the unit guard of 0012: a percentage
typed as a number must be refused. 0012's `charge_rates_unit` only stops values of 0.01 and above, so 0.003 typed for
stamp duty's 0.003% (100x the real 0.00003) or 0.0001 typed for SEBI's 0.0001% (100x the real 0.000001) passed.

Changes: one added CHECK, `charge_rates_unit_caps`: sebi_rate < 0.00001 and stamp_buy_rate < 0.0001 (about 3x the real
rates), every other component unconstrained by it. 0012 is not amended (already merged); the seed rows (0.000001 and
0.00003) satisfy it. Downgrade drops the constraint.

Chain note: revises 0013_exchange_freeze_limits (re-chained after W-076 merged). It adds no allowlist block.

Revision ID: 0014_charge_rates_caps
Revises: 0013_exchange_freeze_limits
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0014_charge_rates_caps"
down_revision = "0013_exchange_freeze_limits"
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


# The predecessor is read from down_revision (the way 0013 does): a re-chain changes that one line. This migration adds
# no allowlist block (a CHECK constraint is not a privilege), so its allowlist function is its predecessor's, unchanged,
# and a later migration can chain on this one through ``_M8`` and ``extended_allowlist_sql``.
_PREVIOUS = _load(f"{down_revision}.py", "ofo_migration_predecessor_for_0014")
_M8 = _PREVIOUS._M8


def extended_allowlist_sql() -> str:
    """This migration's allowlist function text: the predecessor's (no block 15 is added here). The next one chains."""
    return _PREVIOUS.extended_allowlist_sql()

TABLE = "public.charge_rates"
CONSTRAINT = "charge_rates_unit_caps"
SEBI_CAP = "0.00001"  # ofo.charges.rates.SEBI_CAP; a test asserts the two equal
STAMP_CAP = "0.0001"  # ofo.charges.rates.STAMP_CAP


def upgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE {TABLE} ADD CONSTRAINT {CONSTRAINT} CHECK (
            CASE component WHEN 'sebi_rate' THEN value < {SEBI_CAP}
                           WHEN 'stamp_buy_rate' THEN value < {STAMP_CAP}
                           ELSE TRUE END)
        """
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT {CONSTRAINT}")
