"""REQ-081 AC-2 / ADR-167 (2): the round-trip charges of the real 2026-10-15 condor itemised by component.

Core: round_trip_breakdown on that condor equals the hand arithmetic of test_charges_in_sentences (brokerage 160, STT
16.55, exchange 7.84, SEBI 0.02, stamp 0.33, GST 30.22; total 214.96, rounded UP once).
Proof: test_components_equal_the_hand_arithmetic.
"""
import sys
from decimal import Decimal as D
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ofo.charges.round_trip import ChargesNotComputable, round_trip_breakdown, round_trip_charges
from ofo.engine.legs import Action, Instrument, Leg
from test_charges_in_sentences import EXPIRY, HAND_PAISE, RATES, Q, legs

HAND = {"brokerage": D("160.00"), "stt": D("16.55"), "exchange_transaction": D("7.84"), "sebi": D("0.02"),
        "stamp": D("0.33"), "gst": D("30.22")}  # test_charges_in_sentences.py docstring, rounded half-even to the paisa
ONE_PAISE = D("0.01")


def test_components_equal_the_hand_arithmetic():
    b = round_trip_breakdown(legs(), "NIFTY", RATES)
    for name, expected in HAND.items():
        assert getattr(b, name) == expected, name
    assert b.total == HAND_PAISE and b.read_on == RATES.read_on


def _parts(b):
    return b.brokerage + b.stt + b.exchange_transaction + b.sebi + b.stamp + b.gst


def test_shown_items_sum_exactly_to_the_shown_total():
    """MINOR (a): one figure, no Rs 0.01-0.02 gap; the exact round trip is within two paise of it (never far off)."""
    b = round_trip_breakdown(legs(), "NIFTY", RATES)
    assert _parts(b) == b.total == HAND_PAISE
    assert abs(b.total - round_trip_charges(legs(), "NIFTY", RATES)) <= 2 * ONE_PAISE


def test_a_case_that_differed_before_now_sums():
    """Hand: one sold CE 100.37 x 65 -> parts rounded each half-even differ from the exact total rounded up."""
    one = (Leg(Action.SELL, Instrument.CE, D("23000"), EXPIRY, Q, D("100.37")),)
    b = round_trip_breakdown(one, "NIFTY", RATES)
    assert _parts(b) == b.total


def test_exercise_stt_line_has_the_rate_and_no_amount_when_a_bought_option_is_held():
    b = round_trip_breakdown(legs(), "NIFTY", RATES)  # the condor holds two bought options
    assert b.exercise_stt_rate == RATES.stt_exercise_rate == D("0.0015")
    assert b.total == HAND_PAISE  # the line is not part of the total


def test_no_exercise_stt_line_without_a_bought_option():
    sold = tuple(x for x in legs() if x.action is Action.SELL)
    assert round_trip_breakdown(sold, "NIFTY", RATES).exercise_stt_rate is None


def test_a_futures_leg_gives_no_breakdown_not_a_partial_one():
    fut = Leg(Action.BUY, Instrument.FUT, None, EXPIRY, Q, D("23000"))
    with pytest.raises(ChargesNotComputable):
        round_trip_breakdown((fut, *legs()), "NIFTY", RATES)
    with pytest.raises(ChargesNotComputable):
        round_trip_breakdown(legs(), "MIDCPNIFTY", RATES)
