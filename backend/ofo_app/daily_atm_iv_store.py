"""The app's own ATM IV, once per underlying per trading day (ADR-277 (4); migration 0047: insert-only guard, one
row per underlying per day), so a true IV percentile can replace the stand-in later.

- record: validated before the database (underlying NIFTY / SENSEX, dates ``datetime.date``, atm_iv a finite exact
  Decimal > 0, never a float) -> ``ValueError``. ``ON CONFLICT DO NOTHING``: the first value of the day is kept;
  returns True when this call inserted the row, False when the day was already stored.
- read_since: answer states - rows -> [(trading_day, atm_iv)] ascending by day; none -> []; a read that fails or a
  value that is not an exact Decimal -> ``DailyAtmIvUnreadable`` (the caller fails closed, never a default).
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text

UNDERLYINGS = ("NIFTY", "SENSEX")
_INSERT = text(
    "INSERT INTO public.daily_atm_iv (underlying, trading_day, expiry, atm_iv) "
    "VALUES (:underlying, :trading_day, :expiry, :atm_iv) ON CONFLICT (underlying, trading_day) DO NOTHING")
_SELECT = text("SELECT trading_day, atm_iv FROM public.daily_atm_iv "
               "WHERE underlying = :underlying AND trading_day >= :since ORDER BY trading_day")


class DailyAtmIvUnreadable(Exception):
    """The stored daily ATM IVs could not be read (fail closed)."""


def _is_date(value: object) -> bool:
    return isinstance(value, datetime.date) and not isinstance(value, datetime.datetime)


def _check(underlying: object, trading_day: object, expiry: object, atm_iv: object) -> None:
    if underlying not in UNDERLYINGS:
        raise ValueError(f"underlying must be one of {UNDERLYINGS}, got {underlying!r}")
    if not (_is_date(trading_day) and _is_date(expiry)):
        raise ValueError("trading_day and expiry must be datetime.date")
    if not isinstance(atm_iv, Decimal) or not atm_iv.is_finite() or atm_iv <= 0:
        raise ValueError(f"atm_iv must be a finite Decimal > 0, got {atm_iv!r}")


async def record(conn: Any, underlying: str, trading_day: datetime.date, expiry: datetime.date,
                 atm_iv: Decimal) -> bool:
    """Stores the day's ATM IV unless the day is already stored (the first value is kept). The caller commits."""
    _check(underlying, trading_day, expiry, atm_iv)
    result = await conn.execute(_INSERT, {"underlying": underlying, "trading_day": trading_day, "expiry": expiry,
                                          "atm_iv": atm_iv})
    return result.rowcount == 1


async def read_since(conn: Any, underlying: str, since: datetime.date) -> list[tuple[datetime.date, Decimal]]:
    """The stored (trading_day, atm_iv) from ``since`` on, ascending; ``DailyAtmIvUnreadable`` when unreadable."""
    try:
        rows = (await conn.execute(_SELECT, {"underlying": underlying, "since": since})).all()
    except Exception as exc:  # noqa: BLE001 - any read failure is "unreadable", named by the caller
        raise DailyAtmIvUnreadable(f"{underlying}: {type(exc).__name__}") from None
    if any(not isinstance(r.atm_iv, Decimal) for r in rows):
        raise DailyAtmIvUnreadable(f"{underlying}: a stored ATM IV is not an exact Decimal")
    return [(r.trading_day, r.atm_iv) for r in rows]
