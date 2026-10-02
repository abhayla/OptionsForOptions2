"""ORM models. Alembic's env imports this module explicitly; the schema itself comes only from migrations."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, Numeric, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ofo_app.db import Base


class LedgerEntry(Base):
    """The generic append-only ledger base (REQ-064 AC-2).

    recorded_at is stamped by the database (BEFORE INSERT trigger ledger_entries_trusted_clock, migration
    0001_baseline); the server_default convention is from abhayla/algochanakya@bf9faf7:backend/app/models/users.py:20.
    The application role holds only SELECT and INSERT on this table.
    """

    __tablename__ = "ledger_entries"
    # Always schema-qualified, so a same-named temp table can never shadow the ledger.
    __table_args__ = {"schema": "public"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class CatalogueContract(Base):
    """One NIFTY (NFO) or SENSEX (BFO) option or future contract (REQ-053 AC-2; migration 0003_catalogue_store).

    Copied/adapted from abhayla/algochanakya@bf9faf7:backend/app/models/instruments.py (ADR-047, legacy-reuse.md M2):
    strike NUMERIC(12,2) and tick_size NUMERIC(10,4) as Decimal with no float default (legacy: DECIMAL(10,2) and
    default=0.05), unique (exchange, instrument_token) instead of (instrument_token, source_broker), no source_broker
    and no option_type; currently_listed / first_seen_at / last_seen_at added, the stamps set by the database
    trigger catalogue_contracts_guard. Rows are never deleted; a contract's identity never changes, its revisable
    terms (lot_size, tick_size, expiry, tradingsymbol) follow Zerodha with each change recorded in
    public.catalogue_term_changes (Q257). Eligibility is not stored here. Reads and writes go through
    ofo_app.catalogue_store.
    """

    __tablename__ = "catalogue_contracts"
    __table_args__ = (
        UniqueConstraint("exchange", "instrument_token", name="catalogue_contracts_exchange_token_key"),
        {"schema": "public"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exchange: Mapped[str] = mapped_column(Text, nullable=False)
    instrument_token: Mapped[int] = mapped_column(BigInteger, nullable=False)
    exchange_token: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tradingsymbol: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    strike: Mapped[Decimal] = mapped_column(Numeric(12, 2, asdecimal=True), nullable=False, server_default=text("0"))
    tick_size: Mapped[Decimal] = mapped_column(Numeric(10, 4, asdecimal=True), nullable=False)
    lot_size: Mapped[int] = mapped_column(Integer, nullable=False)
    instrument_type: Mapped[str] = mapped_column(Text, nullable=False)
    segment: Mapped[str] = mapped_column(Text, nullable=False)
    currently_listed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
