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


def test_total_is_the_one_exact_round_up_figure_and_each_item_is_within_a_paisa():
    """ADR-082 line 39: total = exact sum rounded UP = round_trip_charges = the scenario block's figure."""
    b = round_trip_breakdown(legs(), "NIFTY", RATES)
    assert b.total == round_trip_charges(legs(), "NIFTY", RATES) == HAND_PAISE
    exact = {"brokerage": D("160"), "stt": D("16.550625"), "exchange_transaction": D("7.84058275"),
             "sebi": D("0.0220675"), "stamp": D("0.3310125"), "gst": D("30.215277045")}  # test_charges_in_sentences
    for name, value in exact.items():
        assert abs(getattr(b, name) - value) <= ONE_PAISE, name


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
