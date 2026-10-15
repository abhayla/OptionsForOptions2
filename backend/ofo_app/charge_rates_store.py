"""Charge rates store: the rate set in force on a day, and the admin write of a new dated set (W-074, ADR-082).

Spec basis: ADR-082 ("The rates are admin settings with the date they were read; every amount is exact Decimal; STT
and stamp duty are not rounded at order level"); ADR-023 (the database clock decides "today"). Table: migration 0012.

Fail closed: a day before the first stored set, a component with no row, or a duplicate (component, date) raises
``ChargeRatesError``; no default rate exists anywhere. Both functions leave transaction control to the caller.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from ofo.charges import ChargeRates

#: Stored component names (migration 0012 COMPONENTS; a test pins them equal).
COMPONENTS = ("brokerage_per_order", "stt_sell_rate", "stt_exercise_rate", "transaction_rate_nse_fo",
              "transaction_rate_bse_fo", "sebi_rate", "stamp_buy_rate", "gst_rate")
MAX_NOTE = 500
IST = "Asia/Kolkata"

_TODAY = text(f"SELECT (clock_timestamp() AT TIME ZONE '{IST}')::date")
_IN_FORCE = text(
    """
    WITH day AS (
        SELECT read_on FROM public.charge_rates WHERE read_on <= :on
        GROUP BY read_on HAVING count(*) = :n ORDER BY read_on DESC LIMIT 1
    )
    SELECT c.component, c.read_on, c.value, c.source_url
    FROM public.charge_rates c JOIN day USING (read_on)
    """
)
_NEWEST = text("SELECT max(read_on) FROM public.charge_rates")
_EXISTS = text("SELECT 1 FROM public.charge_rates WHERE read_on = :on LIMIT 1")
_INSERT = text(
    """
    INSERT INTO public.charge_rates (component, read_on, value, source_url, note)
    VALUES (:component, :read_on, :value, :source_url, :note)
    """
)


class ChargeRatesError(Exception):
    """The stored rates cannot answer, or a write was refused."""


def _values(rates: ChargeRates) -> dict[str, Decimal]:
    return {
        "brokerage_per_order": rates.brokerage_per_order,
        "stt_sell_rate": rates.stt_sell_rate,
        "stt_exercise_rate": rates.stt_exercise_rate,
        "transaction_rate_nse_fo": rates.transaction_rates["NSE_FO"],
        "transaction_rate_bse_fo": rates.transaction_rates["BSE_FO"],
        "sebi_rate": rates.sebi_rate,
        "stamp_buy_rate": rates.stamp_buy_rate,
        "gst_rate": rates.gst_rate,
    }


async def rates_in_force(session: AsyncSession | AsyncConnection, on: date | None = None) -> ChargeRates:
    """The newest COMPLETE set (every component, all from one date) dated on or before ``on`` (default: today by the
    database's IST calendar). A set dated after ``on`` is not in force; a mixed-date answer is impossible."""
    if on is None:
        on = (await session.execute(_TODAY)).scalar_one()
    if not isinstance(on, date) or hasattr(on, "hour"):
        raise ChargeRatesError("the day must be a date")
    rows = (await session.execute(_IN_FORCE, {"on": on, "n": len(COMPONENTS)})).all()
    found = {r.component: r for r in rows}
    missing = [c for c in COMPONENTS if c not in found]
    if missing:
        raise ChargeRatesError(f"no complete charge rate set in force on {on}; missing: {', '.join(missing)}")
    if len({r.read_on for r in rows}) != 1 or len({r.source_url for r in rows}) != 1:
        raise ChargeRatesError(f"the charge rate set in force on {on} mixes dates or source URLs")
    newest = rows[0]
    values = {c: found[c].value for c in COMPONENTS}
    if not all(isinstance(v, Decimal) for v in values.values()):
        raise ChargeRatesError("a stored rate did not come back as an exact Decimal")
    return ChargeRates(
        brokerage_per_order=values["brokerage_per_order"],
        stt_sell_rate=values["stt_sell_rate"],
        stt_exercise_rate=values["stt_exercise_rate"],
        transaction_rates={"NSE_FO": values["transaction_rate_nse_fo"], "BSE_FO": values["transaction_rate_bse_fo"]},
        sebi_rate=values["sebi_rate"],
        stamp_buy_rate=values["stamp_buy_rate"],
        gst_rate=values["gst_rate"],
        read_on=newest.read_on,
        source_url=newest.source_url,
    )


async def add_rate_set(session: AsyncSession | AsyncConnection, rates: ChargeRates, note: str = "") -> None:
    """Admin write: append the whole set (one row per component) dated ``rates.read_on``. A date that already holds a
    set is refused (history is append-only; a correction is a set on a later date)."""
    if not isinstance(rates, ChargeRates):
        raise ChargeRatesError("a ChargeRates value is required")
    if not isinstance(note, str) or len(note) > MAX_NOTE:
        raise ChargeRatesError(f"note must be text of at most {MAX_NOTE} characters")
    if (await session.execute(_EXISTS, {"on": rates.read_on})).first() is not None:
        raise ChargeRatesError(f"a charge rate set dated {rates.read_on} already exists (append-only)")
    newest = (await session.execute(_NEWEST)).scalar_one()
    if newest is not None and rates.read_on < newest:
        raise ChargeRatesError(f"a charge rate set dated {rates.read_on} is older than the newest stored ({newest}): "
                               "back-dating is refused")
    try:
        for component, value in _values(rates).items():
            await session.execute(_INSERT, {"component": component, "read_on": rates.read_on, "value": value,
                                            "source_url": rates.source_url, "note": note})
    except IntegrityError as exc:  # a concurrent write of the same date won the race
        raise ChargeRatesError(f"a charge rate set dated {rates.read_on} already exists (append-only)") from exc
