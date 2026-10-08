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
- catalogue_contracts_supported_underlying also admits exactly the two index rows the domain defines
  (ofo.instruments.models.INDEX_ROWS: NIFTY 50 / NSE_INDEX, SENSEX / BSE_INDEX; a test asserts equal), and the
  instrument-type CHECK admits INDEX only on an index segment (CE / PE / FUT stay derivative-only).
- public.broker_instruments: lot_size and tick_size stay > 0 for every row except Zerodha's INDICES segment, where an
  index row has no lot and no tick (0 allowed there only). The broker table does not hold the platform segment, so the
  CHECK reads the broker's own segment code; the contract-side CHECKs above keep an option out of an index segment.
- Downgrade: refuses while any contract uses NSE_INDEX or BSE_INDEX (rows are never deleted), then restores the
  previous CHECKs.

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


#: The index rows (ofo.instruments.models.INDEX_ROWS: name, segment) and the derivative pairs (0004's SUPPORTED).
INDEX_PAIRS = (("NIFTY 50", "NSE_INDEX"), ("SENSEX", "BSE_INDEX"))
INSTRUMENT_TYPES = ("CE", "PE", "FUT")
INDEX_TYPE = "INDEX"
#: Zerodha's `segment` value of an index row; the broker row carries it as broker_segment.
INDEX_BROKER_SEGMENT = "INDICES"
BROKER_TABLE = _M5.BROKER_TABLE
SUPPORTED_CONSTRAINT = "catalogue_contracts_supported_underlying"
TYPE_CONSTRAINT = "catalogue_contracts_instrument_type_check"
LOT_CONSTRAINT = "broker_instruments_lot_size_check"
TICK_CONSTRAINT = "broker_instruments_tick_size_check"


def _drop_checks_on(table: str, column: str) -> str:
    """Drops every CHECK on `table` that mentions `column` (by its definition, so a differing auto-generated name cannot
    leave the old rule in place), then the caller adds the new one. Fails closed if none was found to drop."""
    return f"""
        DO $drop$
        DECLARE
            c RECORD;
            dropped INTEGER := 0;
        BEGIN
            FOR c IN SELECT conname FROM pg_constraint
                     WHERE conrelid = '{table}'::regclass AND contype = 'c'
                       AND pg_get_constraintdef(oid) ~ '(^|[^a-z_]){column}([^a-z_]|$)' LOOP
                EXECUTE format('ALTER TABLE {table} DROP CONSTRAINT %I', c.conname);
                dropped := dropped + 1;
            END LOOP;
            IF dropped <> 1 THEN
                RAISE EXCEPTION 'expected exactly one CHECK on {table}.{column}, dropped %', dropped;
            END IF;
        END
        $drop$;
        """


def _pairs(pairs: tuple[tuple[str, str], ...]) -> str:
    return " OR ".join(f"(name = '{n}' AND exchange_segment = '{s}')" for n, s in pairs)


def _set_checks(segments: tuple[str, ...], with_index: bool) -> list[str]:
    deriv = tuple(s for n, s in SUPPORTED)
    pairs = _pairs(tuple(SUPPORTED) + (INDEX_PAIRS if with_index else ()))
    types = _M4._quoted(INSTRUMENT_TYPES)
    type_rule = (f"(exchange_segment IN ({_M4._quoted(deriv)}) AND instrument_type IN ({types})) "
                 f"OR (exchange_segment IN ({_M4._quoted(INDEX_SEGMENTS)}) AND instrument_type = '{INDEX_TYPE}')"
                 if with_index else f"instrument_type IN ({types})")
    lot_rule = f"lot_size > 0 OR (broker_segment = '{INDEX_BROKER_SEGMENT}' AND lot_size = 0)" if with_index else "lot_size > 0"
    tick_rule = (f"(tick_size > 0 AND tick_size <> 'NaN') OR (broker_segment = '{INDEX_BROKER_SEGMENT}' AND tick_size = 0)"
                 if with_index else "tick_size > 0 AND tick_size <> 'NaN'")
    return [
        f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {SEGMENT_CONSTRAINT}",
        f"ALTER TABLE {TABLE} ADD CONSTRAINT {SEGMENT_CONSTRAINT} "
        f"CHECK (exchange_segment IN ({_M4._quoted(segments)}))",
        f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {SUPPORTED_CONSTRAINT}",
        f"ALTER TABLE {TABLE} ADD CONSTRAINT {SUPPORTED_CONSTRAINT} CHECK ({pairs})",
        _drop_checks_on(TABLE, "instrument_type"),
        f"ALTER TABLE {TABLE} ADD CONSTRAINT {TYPE_CONSTRAINT} CHECK ({type_rule})",
        _drop_checks_on(BROKER_TABLE, "lot_size"),
        f"ALTER TABLE {BROKER_TABLE} ADD CONSTRAINT {LOT_CONSTRAINT} CHECK ({lot_rule})",
        _drop_checks_on(BROKER_TABLE, "tick_size"),
        f"ALTER TABLE {BROKER_TABLE} ADD CONSTRAINT {TICK_CONSTRAINT} CHECK ({tick_rule})",
    ]


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(f"LOCK TABLE {TABLE}, {BROKER_TABLE} IN ACCESS EXCLUSIVE MODE")
    for statement in _set_checks(EXCHANGE_SEGMENTS, True):
        op.execute(statement)
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    op.execute(
        f"""
        DO $down$
        DECLARE
            uses_index BOOLEAN := FALSE;
        BEGIN
            EXECUTE 'LOCK TABLE {TABLE}, {BROKER_TABLE} IN ACCESS EXCLUSIVE MODE';
            EXECUTE 'SELECT EXISTS (SELECT 1 FROM {TABLE} WHERE exchange_segment IN ({_M4._quoted(INDEX_SEGMENTS)}))'
                INTO uses_index;
            IF uses_index THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: the catalogue holds index contracts (never deleted)';
            END IF;
        END
        $down$;
        """
    )
    for statement in _set_checks(PREVIOUS_SEGMENTS, False):
        op.execute(statement)
    role = _BASE._app_role()
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
