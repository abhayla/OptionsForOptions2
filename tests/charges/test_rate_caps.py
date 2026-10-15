"""W-074 verifier MINOR D1 (W-075): a percentage typed as a number is refused for stamp and SEBI too, not only above the
1% cap. Real rates: stamp 0.00003 (0.003%), SEBI 0.000001 (Rs 10 per crore); caps about 3x each: stamp < 0.0001,
SEBI < 0.00001. Typing the percent figure (0.003 for stamp, 0.0001 for SEBI) passed the old 1% cap and is now refused."""
from dataclasses import replace
from datetime import date
from decimal import Decimal as D

import pytest

from ofo.charges import ChargeRates

REAL = ChargeRates(
    brokerage_per_order=D("20"), stt_sell_rate=D("0.0015"), stt_exercise_rate=D("0.0015"),
    transaction_rates={"NSE_FO": D("0.0003553"), "BSE_FO": D("0.000325")}, sebi_rate=D("0.000001"),
    stamp_buy_rate=D("0.00003"), gst_rate=D("0.18"), read_on=date(2026, 10, 15), source_url="https://zerodha.com/charges")


def test_real_rates_are_accepted():
    replace(REAL)


@pytest.mark.parametrize("field,typed", [("stamp_buy_rate", "0.003"), ("stamp_buy_rate", "0.0001"),
                                         ("sebi_rate", "0.0001"), ("sebi_rate", "0.00001")])
def test_a_percentage_typed_as_a_number_is_refused(field, typed):
    with pytest.raises(ValueError, match=field):
        replace(REAL, **{field: D(typed)})


@pytest.mark.parametrize("field,top", [("stamp_buy_rate", "0.00009"), ("sebi_rate", "0.000009")])
def test_just_under_the_cap_is_accepted(field, top):
    assert getattr(replace(REAL, **{field: D(top)}), field) == D(top)


def test_the_migration_carries_the_same_caps_as_the_code():
    import re
    from pathlib import Path

    from ofo.charges.rates import SEBI_CAP, STAMP_CAP
    text = (Path(__file__).resolve().parents[2] / "backend" / "ofo_app" / "alembic" / "versions"
            / "0014_charge_rates_caps.py").read_text(encoding="utf-8")
    assert D(re.search(r'^SEBI_CAP = "([\d.]+)"', text, re.M).group(1)) == SEBI_CAP
    assert D(re.search(r'^STAMP_CAP = "([\d.]+)"', text, re.M).group(1)) == STAMP_CAP
    assert 'down_revision = "0012_charge_rates"' in text
