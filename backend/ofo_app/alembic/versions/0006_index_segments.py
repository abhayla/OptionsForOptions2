"""Index segments: the catalogue's exchange-segment CHECK gains NSE_INDEX and BSE_INDEX (W-060, REQ-072 AC-1).

Spec basis: REQ-072 AC-1 ("The platform's segment list gains NSE_INDEX and BSE_INDEX for the two index rows only
(NIFTY 50, SENSEX); their identity is (segment, exchange token)..."); REQ-054 "Exchange segment vocabulary"; the domain
list is ofo.instruments.models.EXCHANGE_SEGMENTS = {NSE_FO, BSE_FO, NSE_INDEX, BSE_INDEX}.

Copy from: none - follows 0005_contract_lifecycle.py (module constants, chained loading, refusing downgrade).

Changes (owner-run, one transaction):
- public.catalogue_contracts: catalogue_contracts_exchange_segment_check is replaced by a CHECK over the four
  segments. Nothing else changes: no column, grant, index, guard function or trigger, so the allowlist function and the
  pinned guard bodies are exactly 0005's. The identity key (live (exchange_segment, exchange_token)) already covers the
  new segments.
- Not changed here (named gap, for the work item): catalogue_contracts_supported_underlying still admits only the two
  derivative (name, segment) pairs, and broker_instruments still requires lot_size > 0 and tick_size > 0, so an index row
  (lot 0, tick 0 in the domain model) is not yet storable. This migration widens the segment vocabulary only.
- Downgrade: refuses while any contract uses NSE_INDEX or BSE_INDEX (rows are never deleted), then restores the
  two-segment CHECK.

Revision ID: 0006_index_segments
Revises: 0005_contract_lifecycle
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0006_index_segments"
down_revision = "0005_contract_lifecycle"
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


_M5 = _load("0005_contract_lifecycle.py", "ofo_migration_0005_for_0006")
_M4 = _M5._M4
_BASE = _M5._BASE

TABLE = _M5.TABLE
SEGMENT_CONSTRAINT = "catalogue_contracts_exchange_segment_check"

#: Segments before this migration (0004's) and the platform's list after it (ofo.instruments.models; a test asserts equal).
PREVIOUS_SEGMENTS = _M5.EXCHANGE_SEGMENTS
INDEX_SEGMENTS = ("NSE_INDEX", "BSE_INDEX")
EXCHANGE_SEGMENTS = PREVIOUS_SEGMENTS + INDEX_SEGMENTS

# Unchanged from 0005; exposed so the scope test can point at the head.
ZERODHA_EXCHANGE_TO_SEGMENT = _M5.ZERODHA_EXCHANGE_TO_SEGMENT
BROKER_CODES = _M5.BROKER_CODES
SUPPORTED = _M5.SUPPORTED
PINNED_BODIES = _M5.PINNED_BODIES
ALLOWLIST_BLOCK_MARKER = _M5.ALLOWLIST_BLOCK_MARKER


#: Every other public constant of 0005 (guard names, column lists, markers) is this schema's too: the guards, grants and
#: allowlist are untouched, so tests that read "the head" see the same values.
for _name in dir(_M5):
    if not _name.startswith("_") and _name not in globals():
        globals()[_name] = getattr(_M5, _name)
del _name

#: The allowlist function is not changed by this migration: these are 0005's, so the chain stays one lineage.
extend_allowlist = _M5.extend_allowlist
previous_allowlist_sql = _M5.previous_allowlist_sql
extended_allowlist_sql = _M5.extended_allowlist_sql


def _set_segment_check(segments: tuple[str, ...]) -> list[str]:
    return [
        f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {SEGMENT_CONSTRAINT}",
        f"ALTER TABLE {TABLE} ADD CONSTRAINT {SEGMENT_CONSTRAINT} "
        f"CHECK (exchange_segment IN ({_M4._quoted(segments)}))",
    ]


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(f"LOCK TABLE {TABLE} IN ACCESS EXCLUSIVE MODE")
    for statement in _set_segment_check(EXCHANGE_SEGMENTS):
        op.execute(statement)
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    op.execute(
        f"""
        DO $down$
        DECLARE
            uses_index BOOLEAN := FALSE;
        BEGIN
            EXECUTE 'LOCK TABLE {TABLE} IN ACCESS EXCLUSIVE MODE';
            EXECUTE 'SELECT EXISTS (SELECT 1 FROM {TABLE} WHERE exchange_segment IN ({_M4._quoted(INDEX_SEGMENTS)}))'
                INTO uses_index;
            IF uses_index THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: the catalogue holds index contracts (never deleted)';
            END IF;
        END
        $down$;
        """
    )
    for statement in _set_segment_check(PREVIOUS_SEGMENTS):
        op.execute(statement)
    role = _BASE._app_role()
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
