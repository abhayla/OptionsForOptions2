"""charge_segment: the one public rule mapping an underlying to the exchange segment whose charge rates apply."""
from __future__ import annotations

import pytest
from ofo.charges.round_trip import ChargesNotComputable, charge_segment


@pytest.mark.parametrize(("underlying", "segment"), [("NIFTY", "NSE_FO"), ("SENSEX", "BSE_FO")])
def test_each_supported_underlying_has_its_segment(underlying, segment):
    assert charge_segment(underlying) == segment


@pytest.mark.parametrize("underlying", ["BANKNIFTY", "nifty", ""])
def test_an_unknown_underlying_is_refused_never_guessed(underlying):
    with pytest.raises(ChargesNotComputable):
        charge_segment(underlying)
