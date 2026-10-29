"""GC-TP step 1b (REQ-109 AC-1): the engine's rule for a price a user types on a paper order."""
from __future__ import annotations

from decimal import Decimal

import pytest
from ofo.tracking.orderbook import is_typed_price

D = Decimal


@pytest.mark.parametrize("price", ["0.05", "0.10", "10.00", "100.05", "22550.00", "9999999.95", "10000000"])
def test_a_positive_multiple_of_the_tick_within_the_column_is_a_typed_price(price):
    assert is_typed_price(D(price))


@pytest.mark.parametrize("price", ["0", "-0.05", "0.01", "100.03", "100.123", "10000000.05", "NaN", "Infinity"])
def test_zero_negative_off_tick_too_large_and_non_finite_are_refused(price):
    assert not is_typed_price(D(price))


def test_a_float_or_a_string_is_never_a_typed_price():
    assert not is_typed_price(100.05)  # type: ignore[arg-type]
    assert not is_typed_price("100.05")  # type: ignore[arg-type]
