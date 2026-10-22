"""W-125 (REQ-079 AC-3, AC-6, AC-7, AC-8; ADR-150 (2), ADR-157): strikes placed by a fixed rule, on the real instrument file.

Core proof (step 1): NIFTY at spot 22,810 (strike gap 50 from the recorded file), "Bull call spread" loads
BUY 22,800 CE / SELL 23,000 CE; strangle distance 100, SELL side, loads SELL 22,700 PE / SELL 22,900 CE (REQ-079 AC-3
and AC-7 examples). Expected strikes are hand computed from the spec examples: ATM = nearest listed strike to 22,810 =
22,800; bull call spread width is the catalogue's 4 steps x 50 = 200 points.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from ofo.engine.legs import Action, Instrument
from ofo.instruments.catalogue import Catalogue
from ofo.instruments.parser import parse_instruments_csv
from ofo.strategy.loader import load_templates
from ofo.strategy.placement import (
    QUICK_PICK_DISTANCES,
    PlacedLeg,
    PlacementRefused,
    Refusal,
    expiry_slots,
    listed_atm,
    place_quick_pick,
    place_template,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "instruments" / "instruments_slice.csv"
NEAR, NEXT = date(2026, 9, 29), date(2026, 10, 6)
GAP = Decimal(50)
SPOT = Decimal("22810")
D = Decimal
BY_ID = {t.id: t for t in load_templates()}


@pytest.fixture(scope="module")
def listed() -> dict[date, set[Decimal]]:
    cat = Catalogue()
    cat.load(parse_instruments_csv(FIXTURE))
    out: dict[date, set[Decimal]] = defaultdict(set)
    for e in cat.all_entries():
        c = e.contract
        if c.name == "NIFTY" and c.instrument_type in ("CE", "PE"):
            out[c.expiry].add(c.strike)
    return dict(out)


def _place(template_id, listed, *, spot=SPOT, fresh=True, chosen=NEAR):
    return place_template(BY_ID[template_id], expiries=expiry_slots(chosen, sorted(listed)), spot=spot,
                          spot_fresh=fresh, strike_gap=GAP, listed_strikes=listed)


def _legs(placed):
    return [(p.action.value, p.instrument.value, p.strike) for p in placed]


def test_core_bull_call_spread_and_strangle_load_the_spec_examples_on_the_real_file(listed):
    """Core / AC-3 / AC-7: NIFTY 22,810 -> BUY 22800 CE / SELL 23000 CE; strangle 100 SELL -> SELL 22700 PE / SELL 22900 CE."""
    assert _legs(_place("bull_call_spread", listed)) == [("BUY", "CE", D(22800)), ("SELL", "CE", D(23000))]
    pick = place_quick_pick("strangle", underlying="NIFTY", distance=100, side=Action.SELL, expiry=NEAR, spot=SPOT,
                            spot_fresh=True, strike_gap=GAP, listed_strikes=listed[NEAR])
    assert _legs(pick) == [("SELL", "PE", D(22700)), ("SELL", "CE", D(22900))]


def test_ac3_atm_is_the_nearest_listed_strike_and_a_tie_takes_the_lower(listed):
    """AC-3: 22,825 is exactly between 22,800 and 22,850 -> 22,800; just above the midpoint -> 22,850."""
    assert listed_atm(D("22825"), listed[NEAR]) == D(22800)
    assert listed_atm(D("22825.01"), listed[NEAR]) == D(22850)
    assert listed_atm(D("22810"), listed[NEAR]) == D(22800)
    assert listed_atm(D("22825"), {D(22850), D(22800)}) == D(22800)  # the set's order never decides a tie


def test_ac3_atm_is_taken_from_the_listed_strikes_not_a_regular_grid():
    """AC-3: with 22,800 unlisted, spot 22,810 snaps to the nearest LISTED strike."""
    assert listed_atm(D("22810"), {D(22700), D(22850)}) == D(22850)


def test_ac3_every_template_places_on_listed_strikes_at_its_catalogue_offsets(listed):
    """AC-3: all 21 templates place; each strike is a listed strike of its expiry; offsets are the template data."""
    assert len(BY_ID) == 21
    for tid, template in BY_ID.items():
        defaults = {p.name: p.default for p in template.params}
        placed = _place(tid, listed)
        assert len(placed) == len(template.legs), tid
        for leg, tl in zip(placed, template.legs, strict=True):
            if tl.strike is None:
                assert leg.strike is None and leg.instrument is Instrument.FUT
            else:
                assert leg.strike == D(22800) + D(tl.strike.evaluate(defaults)) * GAP, tid
                assert leg.strike in listed[leg.expiry], tid


def test_ac3_bear_put_spread_hand_computed(listed):
    """AC-3: bear put spread = BUY 22800 PE / SELL 22600 PE (4 steps down), hand computed."""
    assert _legs(_place("bear_put_spread", listed)) == [("BUY", "PE", D(22800)), ("SELL", "PE", D(22600))]


def test_ac6_calendar_spread_uses_the_next_listed_expiry(listed):
    """AC-6 / ADR-157: near leg on the chosen expiry, far leg on the next listed one."""
    placed = _place("calendar_spread", listed)
    assert [(p.expiry, p.strike) for p in placed] == [(NEAR, D(22800)), (NEXT, D(22800))]


def test_ac6_a_template_needing_an_expiry_the_file_lacks_is_refused_not_a_crash(listed):
    """AC-6: chosen expiry is the last listed -> calendar spread has no next expiry -> EXPIRY_MISSING."""
    with pytest.raises(PlacementRefused) as e:
        _place("calendar_spread", listed, chosen=NEXT)
    assert e.value.reason is Refusal.EXPIRY_MISSING
    assert expiry_slots(NEXT, sorted(listed)) == {"near": NEXT, "next": None}
    assert _place("bull_call_spread", listed, chosen=NEXT)  # a one-expiry template still loads there


@pytest.mark.parametrize(("spot", "fresh", "reason"), [
    (None, True, Refusal.SPOT_MISSING), (D(0), True, Refusal.SPOT_MISSING), (SPOT, False, Refusal.SPOT_STALE)])
def test_ac8_a_missing_or_stale_spot_places_nothing(listed, spot, fresh, reason):
    """AC-8: no strike is placed from a missing or old spot (templates and quick picks)."""
    with pytest.raises(PlacementRefused) as e:
        _place("bull_call_spread", listed, spot=spot, fresh=fresh)
    assert e.value.reason is reason
    with pytest.raises(PlacementRefused) as e2:
        place_quick_pick("straddle", underlying="NIFTY", distance=0, side=Action.BUY, expiry=NEAR, spot=spot,
                         spot_fresh=fresh, strike_gap=GAP, listed_strikes=listed[NEAR])
    assert e2.value.reason is reason


def test_ac8_a_strike_the_file_does_not_list_is_refused_never_snapped(listed):
    """AC-8 / ADR-008: spot near the top of the 10-06 list makes +200 points fall off it -> STRIKE_NOT_LISTED."""
    with pytest.raises(PlacementRefused) as e:
        _place("bull_call_spread", listed, spot=D("25790"), chosen=NEXT)
    assert e.value.reason is Refusal.STRIKE_NOT_LISTED
    with pytest.raises(PlacementRefused) as e2:
        listed_atm(SPOT, set())
    assert e2.value.reason is Refusal.STRIKE_NOT_LISTED


def test_ac7_straddle_is_both_legs_at_atm_on_the_users_side(listed):
    """AC-7: a straddle at ATM; BUY side is the user's choice."""
    pick = place_quick_pick("straddle", underlying="NIFTY", distance=0, side=Action.BUY, expiry=NEAR, spot=SPOT,
                            spot_fresh=True, strike_gap=GAP, listed_strikes=listed[NEAR])
    assert pick == (PlacedLeg(Action.BUY, Instrument.PE, D(22800), NEAR), PlacedLeg(Action.BUY, Instrument.CE, D(22800), NEAR))


def test_ac7_default_distances_are_the_spec_lists():
    """AC-7: NIFTY 50/100/150/200, SENSEX 100/200/300/400."""
    assert QUICK_PICK_DISTANCES == {"NIFTY": (50, 100, 150, 200), "SENSEX": (100, 200, 300, 400)}


@pytest.mark.parametrize("distance", [0, 25, 75, 250, -100, 400])
def test_ac7_a_distance_not_offered_for_the_underlying_is_refused(listed, distance):
    """AC-7: 400 is a SENSEX distance; 75 is not a multiple of 50 and not offered; negatives are refused."""
    with pytest.raises(PlacementRefused) as e:
        place_quick_pick("strangle", underlying="NIFTY", distance=distance, side=Action.SELL, expiry=NEAR, spot=SPOT,
                         spot_fresh=True, strike_gap=GAP, listed_strikes=listed[NEAR])
    assert e.value.reason is Refusal.DISTANCE_NOT_OFFERED


def test_ac7_an_offered_distance_that_is_not_a_multiple_of_the_strike_step_is_refused(listed):
    """AC-7: distances must be multiples of the strike step: 100 with a step of 30 is refused."""
    with pytest.raises(PlacementRefused) as e:
        place_quick_pick("strangle", underlying="NIFTY", distance=100, side=Action.SELL, expiry=NEAR, spot=SPOT,
                         spot_fresh=True, strike_gap=D(30), listed_strikes=listed[NEAR])
    assert e.value.reason is Refusal.DISTANCE_NOT_OFFERED


def test_ac7_an_unknown_underlying_has_no_distances_and_a_bad_kind_raises(listed):
    """AC-7: no distances for an underlying outside the list; a kind other than straddle/strangle raises."""
    with pytest.raises(PlacementRefused):
        place_quick_pick("strangle", underlying="BANKNIFTY", distance=100, side=Action.SELL, expiry=NEAR, spot=SPOT,
                         spot_fresh=True, strike_gap=GAP, listed_strikes=listed[NEAR])
    with pytest.raises(ValueError, match="straddle"):
        place_quick_pick("iron", underlying="NIFTY", distance=100, side=Action.SELL, expiry=NEAR, spot=SPOT,
                         spot_fresh=True, strike_gap=GAP, listed_strikes=listed[NEAR])
