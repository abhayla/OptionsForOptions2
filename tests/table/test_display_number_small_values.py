"""D-46 (docs/process/ic-live-test-2026-11-23-issues.md, condors C5/C6): a Greek whose real value is not zero but
rounds to zero at the column's places (delta 2, gamma 4) showed "0.00" / "0.0000" / "-0.0001" and hid the real
number. One formatter (ofo.table.model._display_number: table cell, target readout, paper card) keeps up to two
significant digits for such a value, as the chain's gamma already does (chain_push._gamma_shown). A value that
rounds to more than one step shows exactly as before; a true zero stays 0.00 / 0.0000."""
from decimal import Decimal as D

import pytest
from ofo.table.model import display_number


@pytest.mark.parametrize(("value", "places", "shown"), [
    (D("0.004"), 2, "0.004"),          # delta that is not zero but rounds to 0.00
    (D("-0.0049"), 2, "-0.0049"),
    (D("0.00004"), 4, "0.00004"),      # gamma that rounds to 0.0000
    (D("-0.00006"), 4, "-0.00006"),    # what the screen showed as -0.0001, kept as the real two digits
    (D("0.000012345"), 4, "0.000012"),
    (D("0.005"), 2, "0.005"),          # would show as one step (0.01): also keeps its two digits
])
def test_a_real_value_that_rounds_to_zero_shows_two_significant_digits(value: D, places: int, shown: str) -> None:
    assert str(display_number(value, places)) == shown


@pytest.mark.parametrize(("value", "places", "shown"), [
    (D("0"), 2, "0.00"), (D("0.0000"), 4, "0.0000"), (D("-0.0000"), 4, "0.0000"),   # a true zero, never signed
    (D("0.0001"), 4, "0.0001"), (D("-0.0001"), 4, "-0.0001"), (D("0.0150"), 2, "0.02"),  # as before
    (D("12.345"), 2, "12.35"), (D("-65.5"), 2, "-65.50"),
])
def test_everything_else_shows_as_before(value: D, places: int, shown: str) -> None:
    assert str(display_number(value, places)) == shown
