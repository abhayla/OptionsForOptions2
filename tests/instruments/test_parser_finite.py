"""#738: the instrument-file parser refuses a non-finite strike or tick size (Decimal accepts "NaN" / "Infinity"; a
contract with such a strike is no contract, ADR-008: money and prices are exact finite decimals). Every answer state:
finite kept, empty refused (existing), unparseable refused (existing), NaN / sNaN / Infinity / -Infinity refused."""
from __future__ import annotations

from decimal import Decimal

import pytest
from ofo.instruments.parser import parse_instruments_rows

ROW = {"instrument_token": "60818920450", "exchange_token": "73908", "tradingsymbol": "NIFTY26SEP23150CE",
       "name": "NIFTY", "last_price": "0", "expiry": "2026-09-29", "strike": "23150", "tick_size": "0.05",
       "lot_size": "65", "instrument_type": "CE", "segment": "NFO-OPT", "exchange": "NFO"}


def test_a_finite_strike_and_tick_size_still_parse():
    (contract,) = list(parse_instruments_rows([ROW]))
    assert contract.contract.strike == Decimal("23150")


@pytest.mark.parametrize("bad", ["NaN", "nan", "sNaN", "Infinity", "-Infinity", "inf"])
@pytest.mark.parametrize("field", ["strike", "tick_size"])
def test_738_a_non_finite_strike_or_tick_size_is_refused(field, bad):
    with pytest.raises(ValueError, match=f"unparseable {field}"):
        list(parse_instruments_rows([{**ROW, field: bad}]))
