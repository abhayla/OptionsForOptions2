"""ORM models. Alembic's env imports this module explicitly; the schema itself comes only from migrations."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Index, Integer, Numeric, Text, UniqueConstraint, func, text
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
    """One NIFTY (NSE_FO) or SENSEX (BSE_FO) option or future contract, identified by (exchange_segment,
    exchange_token) while it is live (REQ-053 AC-2, REQ-054 AC-3, ADR-057; migrations 0003_catalogue_store,
    0004_broker_instruments and 0005_contract_lifecycle). Links use the internal id.

    Rows are never deleted and their identity never changes (database trigger catalogue_contracts_guard); expiry and
    strike are the revisable columns of a live contract, their changes recorded in public.catalogue_term_changes. Once
    its expiry has passed a contract is retired (never changes again) and its token may be reused by a new contract. No broker's ids live here: Zerodha's
    instrument_token, trading symbol, segment code, lot and tick size are in BrokerInstrument. Reads and writes go
    through ofo_app.catalogue_store.
    """

    __tablename__ = "catalogue_contracts"
    __table_args__ = (
        Index("catalogue_contracts_live_identity_key", "exchange_segment", "exchange_token", unique=True,
              postgresql_where=text("NOT retired AND NOT delisted")),
        {"schema": "public"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exchange_segment: Mapped[str] = mapped_column(Text, nullable=False)
    exchange_token: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    strike: Mapped[Decimal] = mapped_column(Numeric(12, 2, asdecimal=True), nullable=False, server_default=text("0"))
    instrument_type: Mapped[str] = mapped_column(Text, nullable=False)
    currently_listed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    retired: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delisted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    delisted_on: Mapped[date | None] = mapped_column(Date, nullable=True)


class BrokerInstrument(Base):
    """One broker's own row for one contract (REQ-054 AC-3/AC-4; migration 0004_broker_instruments): its token,
    symbol and segment code, and its lot size, tick size and freeze limit dated seen_on (stamped by the database).
    Never deleted; identity (contract, broker, token, segment) never changes; revisable terms keep history."""

    __tablename__ = "broker_instruments"
    __table_args__ = (
        Index("broker_instruments_live_token_key", "broker", "broker_segment", "broker_token", unique=True,
              postgresql_where=text("NOT retired")),
        UniqueConstraint("contract_id", "broker", name="broker_instruments_contract_broker_key"),
        {"schema": "public"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    contract_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    broker: Mapped[str] = mapped_column(Text, nullable=False)
    broker_token: Mapped[str] = mapped_column(Text, nullable=False)
    broker_symbol: Mapped[str] = mapped_column(Text, nullable=False)
    broker_segment: Mapped[str] = mapped_column(Text, nullable=False)
    lot_size: Mapped[int] = mapped_column(Integer, nullable=False)
    tick_size: Mapped[Decimal] = mapped_column(Numeric(10, 4, asdecimal=True), nullable=False)
    freeze_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seen_on: Mapped[date] = mapped_column(Date, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    retired: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
