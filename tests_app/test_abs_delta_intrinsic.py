# ruff: noqa: PLR2004 - the ADR-268 example numbers are the point
"""ADR-268 (1): a leg with no engine delta whose price is within one tick of intrinsic takes delta 1 (in the money) or
0 (out of the money), never "not available"; a stated delta or a price with time value left is unchanged. No DB.
Example from the ADR: expiry day, spot 23,600, sold 23,500 CE worth its intrinsic 100."""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from types import SimpleNamespace

from ofo.adjustment.approaches import PositionLeg
from ofo_app import adjustment_check as check

EXP = datetime.date(2026, 11, 10)


def _leg(kind: str, strike: str) -> PositionLeg:
    return PositionLeg("SELL", kind, D(strike), EXP, 1, D("50"), f"NIFTY{strike}{kind}")


def _market(greeks: dict) -> SimpleNamespace:
    return SimpleNamespace(leg_greeks=greeks)


def test_itm_call_at_intrinsic_is_delta_one():
    assert check._abs_delta(_market({}), _leg("CE", "23500"), D("100"), D("23600")) == D(1)  # noqa: SLF001


def test_itm_call_within_one_tick_of_intrinsic_is_delta_one():
    assert check._abs_delta(_market({}), _leg("CE", "23500"), D("100.05"), D("23600")) == D(1)  # noqa: SLF001


def test_itm_put_at_intrinsic_is_delta_one():
    assert check._abs_delta(_market({}), _leg("PE", "23500"), D("80"), D("23420")) == D(1)  # noqa: SLF001


def test_otm_option_at_zero_is_delta_zero():
    assert check._abs_delta(_market({}), _leg("CE", "24000"), D("0.05"), D("23600")) == D(0)  # noqa: SLF001


def test_time_value_left_stays_not_available():
    assert check._abs_delta(_market({}), _leg("CE", "23500"), D("100.10"), D("23600")) is None  # noqa: SLF001


def test_no_price_or_no_spot_stays_not_available():
    assert check._abs_delta(_market({}), _leg("CE", "23500"), None, D("23600")) is None  # noqa: SLF001
    assert check._abs_delta(_market({}), _leg("CE", "23500"), D("100"), None) is None  # noqa: SLF001


def test_a_stated_delta_wins():
    g = SimpleNamespace(delta=D("-0.42"))
    assert check._abs_delta(_market({"NIFTY23500CE": g}), _leg("CE", "23500"), D("100"), D("23600")) == D("0.42")  # noqa: SLF001
