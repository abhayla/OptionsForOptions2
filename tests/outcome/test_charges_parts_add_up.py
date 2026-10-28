"""F-1 (GC-UI checker run1, 2026-10-28): the charges breakdown adds up to its total; GST is 18% of the SHOWN parts.

Core: the recorded iron condor (total 263.15 vs parts 263.13) and calendar (GST 18.63 vs 18% of shown parts 18.64)
replies, rebuilt from their real legs and the 2026-10-15 rates, give a breakdown whose total == sum(parts) and whose
GST == 18% of (brokerage + exchange transaction + SEBI) as shown. Proof: the two recorded cases below.
Real legs: D:/Abhay/scratch/gcui-checker/run1/{b_iron_condor,c_calendar}/legs.json (NIFTY, lot 65).
"""
import random
from datetime import date
from decimal import ROUND_HALF_UP
from decimal import Decimal as D

import pytest
from ofo.charges.round_trip import round_trip_breakdown, round_trip_charges
from ofo.engine.legs import Action, Instrument, Leg
from test_charges_in_sentences import RATES

Q = 65
E1, E2 = date(2026, 11, 3), date(2026, 11, 9)
PARTS = ("brokerage", "stt", "exchange_transaction", "gst", "stamp", "sebi")

IRON_CONDOR = (  # run1/b_iron_condor/legs.json
    Leg(Action.BUY, Instrument.PE, D("22500"), E1, Q, D("92.25")),
    Leg(Action.SELL, Instrument.PE, D("22600"), E1, Q, D("123.65")),
    Leg(Action.SELL, Instrument.CE, D("22800"), E1, Q, D("155.20")),
    Leg(Action.BUY, Instrument.CE, D("22900"), E1, Q, D("111.30")),
)
CALENDAR = (  # run1/c_calendar/legs.json
    Leg(Action.SELL, Instrument.CE, D("22700"), E1, Q, D("207.45")),
    Leg(Action.BUY, Instrument.CE, D("22700"), E2, Q, D("300.45")),
)
DEBIT_SPREAD_S54 = (  # run1/a_debit_spread_s54 (strategy 54)
    Leg(Action.BUY, Instrument.CE, D("22600"), E1, Q, D("194.40")),
    Leg(Action.SELL, Instrument.CE, D("22800"), E1, Q, D("106.60")),
)


def _sum(b):
    return sum((getattr(b, k) for k in PARTS), D("0"))


def _gst_of_shown(b):
    return (D("0.18") * (b.brokerage + b.exchange_transaction + b.sebi)).quantize(D("0.01"), rounding=ROUND_HALF_UP)


@pytest.mark.parametrize("legs", [IRON_CONDOR, CALENDAR, DEBIT_SPREAD_S54], ids=["condor", "calendar", "s54"])
def test_recorded_strategy_total_is_the_sum_of_its_shown_parts_and_gst_is_18pc_of_shown(legs):
    b = round_trip_breakdown(legs, "NIFTY", RATES)
    assert b.total == _sum(b)
    assert b.gst == _gst_of_shown(b)
    assert round_trip_charges(legs, "NIFTY", RATES) == b.total  # summary.charges, max profit/loss use this total


def test_recorded_condor_figures():
    b = round_trip_breakdown(IRON_CONDOR, "NIFTY", RATES)
    assert (b.brokerage, b.stt, b.exchange_transaction, b.gst, b.stamp, b.sebi) == (
        D("160.00"), D("47.03"), D("22.28"), D("32.82"), D("0.94"), D("0.06"))
    assert b.total == D("263.13")  # was 263.15 (exact sum rounded UP once; parts summed to 263.13)


def test_recorded_calendar_figures():
    b = round_trip_breakdown(CALENDAR, "NIFTY", RATES)
    assert b.gst == D("18.64")  # was 18.63 (18% of the unrounded parts)
    assert b.total == _sum(b)


def test_property_total_equals_sum_of_parts_over_generated_legs():
    rng = random.Random(20261028)  # noqa: S311 - seeded test generator
    for _ in range(400):
        n = rng.randint(1, 4)
        legs = tuple(
            Leg(rng.choice((Action.BUY, Action.SELL)), rng.choice((Instrument.CE, Instrument.PE)),
                D(rng.randrange(21000, 25000, 50)), E1, Q * rng.randint(1, 30),
                D(rng.randint(5, 80000)) / D(100))
            for _ in range(n))
        b = round_trip_breakdown(legs, "NIFTY", RATES)
        assert b.total == _sum(b), legs
        assert b.gst == _gst_of_shown(b), legs
        assert round_trip_charges(legs, "NIFTY", RATES) == b.total
