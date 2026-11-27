"""D-48 (REQ-078 AC-11, AC-12; ADR-330 (42)): change the expiry of one leg or every leg on the REAL instrument fixture.

Core proof: the condor of test_leg_edit (2026-10-06) moved to the fixture's other expiry 2026-09-29 keeps strike, type,
side and lots; a leg whose strike (15000) is listed only on 2026-09-29 refuses the move to 2026-10-06 and NO leg moves.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import pytest
from ofo.engine import Action, Instrument, Leg
from ofo.strategy import leg_edit
from ofo.strategy.leg_edit import EditLeg, LegEditRefused, Listing
from test_leg_edit import CAT, EARLY_EXPIRY, EXPIRY, LISTING, LOT, NIFTY, condor, one

LATE = datetime.date(2026, 10, 7)


def shape(legs):
    return [(x.leg.action, x.leg.instrument, x.leg.strike, x.lots) for x in legs]


def test_core_all_legs_move_to_the_new_expiry_keeping_strike_type_side_and_lots():
    start = condor()
    result = leg_edit.change_expiry(LISTING, NIFTY, start, None, EARLY_EXPIRY)
    assert all(x.leg.expiry == EARLY_EXPIRY for x in result.legs)
    assert shape(result.legs) == shape(start)
    assert result.moved == frozenset({0, 1, 2, 3})
    assert all(x.leg.expiry == EXPIRY for x in start)  # the input is never changed


def test_one_leg_moves_and_the_others_stay_on_their_expiry():
    result = leg_edit.change_expiry(LISTING, NIFTY, condor(), 2, EARLY_EXPIRY)
    assert [x.leg.expiry for x in result.legs] == [EXPIRY, EXPIRY, EARLY_EXPIRY, EXPIRY]
    assert result.moved == frozenset({2})


def test_one_missing_strike_moves_nothing_and_names_the_strike():
    start = [one(Instrument.CE, "23000", EARLY_EXPIRY), one(Instrument.PE, "15000", EARLY_EXPIRY, Action.SELL)]
    with pytest.raises(LegEditRefused) as err:
        leg_edit.change_expiry(LISTING, NIFTY, start, None, EXPIRY)
    assert err.value.template == "leg_edit_expiry_not_listed"
    assert err.value.message.what_happened == "No 15,000 PE is listed for 06 Oct 2026, so leg 2 cannot move there."
    assert [x.leg.expiry for x in start] == [EARLY_EXPIRY, EARLY_EXPIRY]


def test_an_expired_or_unknown_target_expiry_is_refused_naming_a_strike():
    for target in (datetime.date(2026, 9, 1), datetime.date(2030, 1, 1)):
        with pytest.raises(LegEditRefused) as err:
            leg_edit.change_expiry(LISTING, NIFTY, condor(), None, target)
        assert err.value.template == "leg_edit_expiry_not_listed"
    after = Listing(CAT, LATE)  # 2026-09-29 has passed
    with pytest.raises(LegEditRefused):
        leg_edit.change_expiry(after, NIFTY, condor(), None, EARLY_EXPIRY)


def test_a_futures_leg_refuses_the_whole_change():
    fut = EditLeg(Leg(Action.BUY, Instrument.FUT, None, EXPIRY, LOT, D("23000")), 1, 1)
    with pytest.raises(LegEditRefused) as err:
        leg_edit.change_expiry(LISTING, NIFTY, [*condor(), fut], None, EARLY_EXPIRY)
    assert err.value.template == "leg_edit_expiry_futures"


def test_the_same_expiry_moves_nothing_and_a_moved_leg_loses_its_typed_mark():
    same = leg_edit.change_expiry(LISTING, NIFTY, condor(), None, EXPIRY)
    assert same.moved == frozenset()
    typed = [EditLeg(x.leg, 1, 1, True, True) for x in condor()]
    assert not leg_edit.change_expiry(LISTING, NIFTY, typed, 0, EARLY_EXPIRY).legs[0].typed
