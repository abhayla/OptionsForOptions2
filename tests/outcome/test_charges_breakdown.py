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


def test_total_is_the_rounded_up_round_trip_and_parts_are_within_a_paisa_or_two():
    b = round_trip_breakdown(legs(), "NIFTY", RATES)
    assert b.total == round_trip_charges(legs(), "NIFTY", RATES)
    parts = b.brokerage + b.stt + b.exchange_transaction + b.sebi + b.stamp + b.gst
    assert abs(parts - b.total) <= 2 * ONE_PAISE


def test_a_futures_leg_gives_no_breakdown_not_a_partial_one():
    fut = Leg(Action.BUY, Instrument.FUT, None, EXPIRY, Q, D("23000"))
    with pytest.raises(ChargesNotComputable):
        round_trip_breakdown((fut, *legs()), "NIFTY", RATES)
    with pytest.raises(ChargesNotComputable):
        round_trip_breakdown(legs(), "MIDCPNIFTY", RATES)
