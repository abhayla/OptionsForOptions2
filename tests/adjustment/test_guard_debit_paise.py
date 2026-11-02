"""#633: ``guard_debit`` refuses on the exact debit and shows whole paise (the message's Money slots take 2 places)."""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import pytest
from ofo.adjustment import approaches as ap
from ofo.adjustment import liquidity

EXPIRY = datetime.date(2026, 11, 3)


def _builder(limit: str) -> ap._Builder:
    position = ap.Position("NIFTY", 65, "weekly", datetime.date(2026, 11, 2), ())
    limits = liquidity.limits_from_guards({"roll_debit_limit": limit})
    return ap._Builder(position, (), D("23000"), None, object(), limits, None)  # type: ignore[arg-type]


def _buy(price: str, quantity: int) -> ap.Trade:
    return ap.Trade("BUY", "CE", D("23500"), EXPIRY, 1, quantity, D(price), "X")


def test_a_three_decimal_debit_over_the_limit_builds_a_refusal_without_raising_value_error():
    with pytest.raises(ap._Refused) as refused:  # 500.004 > 500.00; before the fix a ValueError (3 places)
        _builder("Rs 500").guard_debit([_buy("100.0008", 5)])
    assert "500" in refused.value.reason


def test_the_decision_uses_the_exact_figure_not_the_rounded_one():
    _builder("Rs 500").guard_debit([_buy("100.00", 5)])  # exactly the limit: allowed
    with pytest.raises(ap._Refused):
        _builder("Rs 500").guard_debit([_buy("100.0008", 5)])  # 500.004 rounds to 500.00 but is over the limit
