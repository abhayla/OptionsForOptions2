"""Charge rates: tighter unit caps for SEBI and stamp duty (W-075; W-074 verifier MINOR D1).

Spec basis: ADR-082 ("The rates are admin settings with the date they were read"); the unit guard of 0012: a percentage
typed as a number must be refused. 0012's `charge_rates_unit` only stops values of 0.01 and above, so 0.003 typed for
stamp duty's 0.003% (100x the real 0.00003) or 0.0001 typed for SEBI's 0.0001% (100x the real 0.000001) passed.

Changes: one added CHECK, `charge_rates_unit_caps`: sebi_rate < 0.00001 and stamp_buy_rate < 0.0001 (about 3x the real
rates), every other component unconstrained by it. 0012 is not amended (already merged); the seed rows (0.000001 and
0.00003) satisfy it. Downgrade drops the constraint.

Chain note: this migration revises 0012_charge_rates. W-076's 0013 also chains on 0012; the orchestrator re-chains
whichever of the two merges second (down_revision only).

Revision ID: 0014_charge_rates_caps
Revises: 0012_charge_rates
"""

from __future__ import annotations

from alembic import op

revision = "0014_charge_rates_caps"
down_revision = "0012_charge_rates"
branch_labels = None
depends_on = None

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
