"""The charge rate set: one dated, validated value (ADR-082: "The rates are admin settings with the date they were
read").

Each rate is a fraction of the premium as a ``Decimal`` (0.15% is ``Decimal("0.0015")``), built from strings. The
NSE transaction rate is ONE rate, 0.03553% (Kite reports it as one ``exchange_turnover_charge``; Zerodha's own split
into 0.03503% + 0.0005% IPFT only belongs in the note of the stored rate). Nothing here has a default value: a rate set
is always supplied, so an unknown rate can never be assumed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import MappingProxyType

#: The exchange segment vocabulary (REQ-054): the closed set of keys of ``transaction_rates``.
SEGMENTS = ("NSE_FO", "BSE_FO")


#: Unit guard: Zerodha prints "0.15%" and an admin may type 0.15 where the fraction 0.0015 is meant (STT 100x). Every
#: percentage-type rate is a fraction below this cap (1%: the real ones are 0.0015, 0.0003553, 0.000001, 0.00003);
#: GST (18%) is a fraction below 1. Brokerage is rupees and has no fraction cap. The DB CHECK carries the same caps.
FRACTION_CAP = Decimal("0.01")
GST_CAP = Decimal("1")


def _rate(name: str, value: object, cap: Decimal | None = None) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, Decimal):
        raise ValueError(f"{name} must be a Decimal built from a string, got {type(value).__name__}")
    if not value.is_finite() or value < 0:
        raise ValueError(f"{name} must be a finite Decimal >= 0, got {value}")
    if cap is not None and value >= cap:
        raise ValueError(f"{name} is a fraction (0.15% is 0.0015) and must be below {cap}, got {value}")
    return value


@dataclass(frozen=True)
class ChargeRates:
    brokerage_per_order: Decimal  # rupees per executed order (flat)
    stt_sell_rate: Decimal  # fraction of the sell premium
    stt_exercise_rate: Decimal  # fraction of the intrinsic value of a bought option that is exercised
    transaction_rates: Mapping[str, Decimal]  # exchange transaction fraction of premium, keyed by SEGMENTS
    sebi_rate: Decimal  # fraction of premium (Rs 10 per crore = 0.000001)
    stamp_buy_rate: Decimal  # fraction of the buy premium
    gst_rate: Decimal  # fraction of brokerage + SEBI + transaction charges
    read_on: date  # the date the rates were read from the published page
    source_url: str

    def __post_init__(self) -> None:
        _rate("brokerage_per_order", self.brokerage_per_order)
        for name, value in (("stt_sell_rate", self.stt_sell_rate), ("stt_exercise_rate", self.stt_exercise_rate),
                            ("sebi_rate", self.sebi_rate), ("stamp_buy_rate", self.stamp_buy_rate)):
            _rate(name, value, FRACTION_CAP)
        _rate("gst_rate", self.gst_rate, GST_CAP)
        if not isinstance(self.transaction_rates, Mapping) or set(self.transaction_rates) != set(SEGMENTS):
            raise ValueError(f"transaction_rates must have exactly the segments {SEGMENTS}")
        frozen = {s: _rate(f"transaction_rates[{s}]", self.transaction_rates[s], FRACTION_CAP) for s in SEGMENTS}
        object.__setattr__(self, "transaction_rates", MappingProxyType(frozen))
        if not isinstance(self.read_on, date) or hasattr(self.read_on, "hour"):
            raise ValueError("read_on must be a date (not a datetime)")
        if not isinstance(self.source_url, str) or not self.source_url.strip():
            raise ValueError("source_url is required: a rate set names where it was read")
