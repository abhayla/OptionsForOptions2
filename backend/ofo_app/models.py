"""ORM models. Alembic's env imports this module explicitly; the schema itself comes only from migrations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Text, func
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

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
