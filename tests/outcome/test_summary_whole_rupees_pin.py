"""D-46 round 2: the builder summary's max profit / max loss text is whole rupees, half-up, from the exact Decimal
(REQ-152 AC-1, AC-3), through the real serializer helper. C7 real case: 1727.36 and 4773.64."""
from decimal import Decimal as D

import pytest

from ofo.engine.display import format_whole_rupees
from ofo.outcome.serialize import _whole


@pytest.mark.parametrize(("exact", "profit_text", "loss_text"), [
    (D("1727.36"), "+1,727", "−1,727"),
    (D("4773.64"), "+4,774", "−4,774"),   # half-up on the magnitude: 4,774, never 4,773
    (D("4773.50"), "+4,774", "−4,774"),
    (D("4773.49"), "+4,773", "−4,773"),
    (D("1727.50"), "+1,728", "−1,728"),
])
def test_max_profit_and_loss_text_is_half_up_whole_rupees(exact: D, profit_text: str, loss_text: str) -> None:
    assert str(_whole(exact, signed=True)) == profit_text
    assert str(_whole(-exact, signed=True)) == loss_text
    assert format_whole_rupees(-exact, signed=False) == loss_text[1:]
