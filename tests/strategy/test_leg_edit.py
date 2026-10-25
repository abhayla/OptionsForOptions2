"""W-148 (REQ-076): the pure leg-edit functions on the REAL instrument-list fixture.

Core proof (REQ-076 AC-1/AC-2): a real NIFTY 23000 CE of the fixture's 2026-10-06 expiry stepped + goes to the next
LISTED strike (23050), is refused at the last listed strike, and only the stepped leg is marked as a new contract (so
only its planned entry is re-captured). Expected strikes come from the fixture's own listing (20800..25800 in steps of
50 on that expiry; 19500 -> 20800 on 2026-09-29, the real far-from-the-money jump), written before the code.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from pathlib import Path

import pytest
from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.engine.metrics import UNLIMITED, strategy_metrics
from ofo.errors import UserFacingError
from ofo.execution.freeze import StoredFreeze
from ofo.instruments import Catalogue, parse_instruments_csv
from ofo.strategy import leg_edit
from ofo.strategy.leg_edit import EditLeg, LegEditRefused, Listing
from ofo.strategy.loader import load_templates
from ofo.strategy.matching import CUSTOM_STRATEGY, Custom, match, protective_keys

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "instruments" / "instruments_slice.csv"
EXPIRY = datetime.date(2026, 10, 6)
EARLY_EXPIRY = datetime.date(2026, 9, 29)
TODAY = datetime.date(2026, 9, 28)  # before both expiries
LOT = 65
NIFTY = "NIFTY"
FIRST_LISTED, LAST_LISTED = D("20800"), D("25800")
INCLUDED_AFTER_UNTICK = 3
SENSEX_LOT = 20
TWO_PROTECTIVE_LEGS = 2
CAT = Catalogue()
CAT.load(parse_instruments_csv(FIXTURE))
LISTING = Listing(CAT, TODAY)


@pytest.fixture(scope="module")
def cat() -> Catalogue:
    return CAT


def one(instrument: Instrument, strike: str | None, expiry=EXPIRY, action=Action.BUY, price="50.00") -> EditLeg:
    return EditLeg(Leg(action, instrument, None if strike is None else D(strike), expiry, LOT, D(price)), 1, 1)


def condor() -> list[EditLeg]:
    rows = [(Action.BUY, Instrument.PE, "22800", "42.50"), (Action.SELL, Instrument.PE, "23000", "86.00"),
            (Action.SELL, Instrument.CE, "23400", "91.50"), (Action.BUY, Instrument.CE, "23600", "44.00")]
    return [EditLeg(Leg(a, i, D(s), EXPIRY, LOT, D(p)), lots=1, base_lots=1) for a, i, s, p in rows]


def strikes(legs) -> list[D]:
    return [x.leg.strike for x in legs]


def test_core_proof_step_moves_a_real_23000_ce_to_the_next_listed_strike(cat):
    """REQ-076 AC-1/AC-2 (core): + moves 23000 CE to 23050 CE; only that leg is re-captured; the last listed strike is
    refused with the reason."""
    legs = [one(Instrument.CE, "23000", price="81.30"), one(Instrument.PE, "22900", price="40.00")]
    result = leg_edit.step_strike(LISTING, NIFTY, legs, 0, 1)
    assert strikes(result.legs) == [D("23050"), D("22900")]
    assert result.moved == frozenset({0})  # AC-2: the other leg is not marked for a new capture
    assert result.legs[1] == legs[1]  # and keeps its planned entry untouched
    assert legs[0].leg.strike == D("23000")  # the input is never changed
    last = [one(Instrument.CE, str(LAST_LISTED))]
    with pytest.raises(LegEditRefused) as err:
        leg_edit.step_strike(LISTING, NIFTY, last, 0, 1)
    assert err.value.template == "leg_edit_no_further_strike"


def test_ac_1_both_edges_futures_and_unlisted_are_refused(cat):
    """REQ-076 AC-1: no step below the first listed strike; a futures leg has no stepper; an unlisted strike is refused
    (never rounded to a neighbour); a past expiry lists nothing."""
    first = [one(Instrument.PE, str(FIRST_LISTED))]
    with pytest.raises(LegEditRefused) as err:
        leg_edit.step_strike(LISTING, NIFTY, first, 0, -1)
    assert err.value.template == "leg_edit_no_further_strike"
    assert leg_edit.step_strike(LISTING, NIFTY, first, 0, 1).legs[0].leg.strike == D("20850")
    with pytest.raises(LegEditRefused) as err:
        leg_edit.step_strike(LISTING, NIFTY, [one(Instrument.FUT, None)], 0, 1)
    assert err.value.template == "leg_edit_futures_no_stepper"
    with pytest.raises(LegEditRefused) as err:
        leg_edit.step_strike(LISTING, NIFTY, [one(Instrument.CE, "23010")], 0, 1)
    assert err.value.template == "leg_edit_strike_not_listed"
    with pytest.raises(LegEditRefused) as err:
        later = Listing(cat, EXPIRY + datetime.timedelta(days=1))
        leg_edit.step_strike(later, NIFTY, [one(Instrument.CE, "23000")], 0, 1)
    assert err.value.template == "leg_edit_strike_not_listed"


def test_ac_1_far_from_the_money_the_step_follows_the_listed_jump(cat):
    """REQ-076 AC-1: where the list jumps (the file lists 19500 then 20800 on 2026-09-29) + goes to the next LISTED
    strike, not strike + 50; SENSEX steps by its own 100."""
    far = [one(Instrument.CE, "19500", expiry=EARLY_EXPIRY)]
    jumped = leg_edit.step_strike(LISTING, NIFTY, far, 0, 1)
    assert strikes(jumped.legs) == [D("20800")]
    back = leg_edit.step_strike(LISTING, NIFTY, jumped.legs, 0, -1)
    assert strikes(back.legs) == [D("19500")]
    sensex_expiry = datetime.date(2026, 10, 8)
    grid = LISTING.strikes("SENSEX", sensex_expiry, Instrument.CE)
    legs = [EditLeg(Leg(Action.BUY, Instrument.CE, grid[10], sensex_expiry, SENSEX_LOT, D("10")), 1, 1)]
    assert leg_edit.step_strike(LISTING, "SENSEX", legs, 0, 1).legs[0].leg.strike == grid[11]
    assert grid[11] - grid[10] == D("100")


def test_ac_4_multiplier_is_base_lots_times_m_and_quantity_from_the_files_lot_size(cat):
    """REQ-076 AC-4/AC-5: lots = base x multiplier; back to 1 restores base; quantity = lots x the file's lot size
    (65 NIFTY, 20 SENSEX); 0, 51, 2.5, '3' and True are refused."""
    legs = [EditLeg(x.leg, lots=2, base_lots=2) for x in condor()]
    three = leg_edit.apply_multiplier(cat, NIFTY, legs, 3)
    assert [x.lots for x in three] == [6] * 4 and [x.leg.quantity for x in three] == [6 * LOT] * 4
    assert [x.lots for x in leg_edit.apply_multiplier(cat, NIFTY, three, 1)] == [2] * 4
    assert [x.lots for x in leg_edit.apply_multiplier(cat, NIFTY, legs, 50)] == [100] * 4
    sensex_expiry = datetime.date(2026, 10, 8)
    s_legs = [EditLeg(Leg(Action.BUY, Instrument.CE, D("80000"), sensex_expiry, SENSEX_LOT, D("10")), 1, 1)]
    assert leg_edit.apply_multiplier(cat, "SENSEX", s_legs, 3)[0].leg.quantity == 3 * SENSEX_LOT
    for bad in (0, 51, True, 2.5, "3", -1):
        with pytest.raises(ValueError):
            leg_edit.apply_multiplier(cat, NIFTY, legs, bad)  # type: ignore[arg-type]


def test_ac_5_a_quantity_not_below_the_stored_freeze_limit_is_blocked_never_split(cat):
    """REQ-076 AC-5 / ADR-092: NIFTY limit 3,511 and lot 65 (ofo.execution.freeze: largest allowed 3,510 = 54 lots):
    54 lots passes, 55 lots (3,575 units) is blocked with the limit; a leg with no stored limit is not blocked."""
    stored = StoredFreeze(3511, LOT, datetime.date(2026, 10, 1))
    for lots, blocked in ((54, False), (55, True)):
        legs = [EditLeg(Leg(Action.BUY, Instrument.CE, D("23000"), EXPIRY, lots * LOT, D("50")), lots, lots)]
        found = leg_edit.freeze_blocks(legs, {0: stored}, {0: "NIFTY2661023000CE"})
        assert (0 in found) is blocked
    assert isinstance(found[0], UserFacingError)
    at_limit = [EditLeg(Leg(Action.BUY, Instrument.CE, D("23000"), EXPIRY, 54 * LOT, D("50")), 54, 54)]
    exact = leg_edit.freeze_blocks(at_limit, {0: StoredFreeze(54 * LOT, LOT, datetime.date(2026, 10, 1))},
                                   {0: "NIFTY2661023000CE"})
    assert 0 in exact and "53 lots" in exact[0].what_happened  # F-36: units equal to the limit are NOT allowed
    assert found[0].what_happened == (
        "NIFTY2661023000CE: 3575 units (55 lots) is not below the exchange freeze limit of 3511 units; the largest "
        "single order allowed is 3510 units (54 lots).")  # hand: 55 x 65 = 3575; (3511 - 1) // 65 x 65 = 3510 = 54 lots
    assert leg_edit.freeze_blocks(legs, {}, {}) == {}  # no stored limit: no block here


def test_ac_6_include_leg_flips_only_that_leg_and_unticked_leaves_the_engine_legs(cat):
    """REQ-076 AC-6: an unticked leg is absent from the engine's legs: no bought wing, max loss is unlimited; the
    input list is unchanged and a non-bool tick is refused."""
    start = condor()
    legs = leg_edit.include_leg(start, 3, False)
    assert [x.included for x in legs] == [True, True, True, False] and all(x.included for x in start)
    included = leg_edit.included_legs(legs)
    assert len(included) == INCLUDED_AFTER_UNTICK
    assert strategy_metrics(Strategy(tuple(x.leg for x in included))).max_loss is UNLIMITED
    with pytest.raises(ValueError):
        leg_edit.include_leg(start, 3, 1)  # type: ignore[arg-type]


def test_ac_8_9_the_matched_name_and_hedge_marks_come_from_the_catalogue_and_change_no_leg(cat):
    """REQ-076 AC-8/AC-9: four legs SELL 22800 PE, BUY 22600 PE, SELL 23200 CE, BUY 23400 CE are an Iron Condor with
    the two BUY legs protective; changing the 23400 CE to a 23200 PE is Custom Strategy with no marks."""
    rows = [(Action.SELL, Instrument.PE, "22800"), (Action.BUY, Instrument.PE, "22600"),
            (Action.SELL, Instrument.CE, "23200"), (Action.BUY, Instrument.CE, "23400")]
    legs = [Leg(a, i, D(s), EXPIRY, LOT, D("50")) for a, i, s in rows]
    spot, gap = D("23000"), D("50")
    found = match(legs, spot=spot, strike_gap=gap, templates=load_templates())
    assert not isinstance(found, Custom) and found.template.id == "iron_condor"
    marks = protective_keys(found)
    assert {(a, i) for a, i, _, _ in marks} == {(Action.BUY, Instrument.PE), (Action.BUY, Instrument.CE)}
    assert len(marks) == TWO_PROTECTIVE_LEGS
    changed = [*legs[:3], Leg(Action.BUY, Instrument.PE, D("23200"), EXPIRY, LOT, D("50"))]
    again = match(changed, spot=spot, strike_gap=gap, templates=load_templates())
    assert isinstance(again, Custom) and CUSTOM_STRATEGY == "Custom Strategy"
    assert legs[3].strike == D("23400")  # naming never changed a leg


def test_ac_6_a_stepped_leg_is_re_captured_and_a_typed_price_is_a_tick_multiple(cat):
    """REQ-076 AC-2 / REQ-077 AC-2: with_entries replaces the stepped leg's entry only and clears the typed mark; a
    typed price must be a positive multiple of the file's 0.05 tick."""
    legs = condor()
    moved = leg_edit.step_strike(LISTING, NIFTY, legs, 1, 1)
    fresh = leg_edit.with_entries(moved.legs, {1: D("62.10")})
    assert [x.leg.entry_price for x in fresh] == [D("42.50"), D("62.10"), D("91.50"), D("44.00")]
    ok = leg_edit.set_typed_price(cat, NIFTY, legs, 1, D("81.35"))
    assert ok[1].leg.entry_price == D("81.35") and ok[1].typed
    assert not leg_edit.with_entries(ok, {1: D("90.00")})[1].typed
    for bad in (D("81.32"), D("0"), D("-0.05")):
        with pytest.raises(LegEditRefused) as err:
            leg_edit.set_typed_price(cat, NIFTY, legs, 1, bad)
        assert err.value.template == "leg_edit_price_not_tick"


@pytest.mark.parametrize("whole_digits", [27, 30])
@pytest.mark.parametrize("as_decimal", [False, True])
def test_an_oversized_typed_price_is_the_price_refusal_never_a_crash(cat, whole_digits, as_decimal):
    """Chunk-2 Tier A review, area A: 27+ whole digits made quantize raise InvalidOperation; any typed price above the
    absurd-price cap is the one price refusal (USER_INPUT_013), the legs unchanged."""
    text = "9" * whole_digits + ".05"
    legs = condor()
    with pytest.raises(LegEditRefused) as err:
        leg_edit.set_typed_price(cat, NIFTY, legs, 1, D(text) if as_decimal else text)
    assert err.value.template == "leg_edit_price_not_tick"
    assert [x.leg.entry_price for x in legs] == [x.leg.entry_price for x in condor()]


def test_a_61_digit_typed_price_is_refused_never_raised(cat):
    """30 whole + 30 fractional digits (61 characters with the point): the longest text the shape check passes."""
    with pytest.raises(LegEditRefused) as err:
        leg_edit.set_typed_price(cat, NIFTY, condor(), 1, "9" * 30 + "." + "5" * 30)
    assert err.value.template == "leg_edit_price_not_tick"


def test_refusals_are_user_facing_catalogue_text(cat):
    """Every refusal renders from the error catalogue (no ad-hoc string) and names the leg."""
    with pytest.raises(LegEditRefused) as err:
        leg_edit.step_strike(LISTING, NIFTY, [one(Instrument.CE, str(LAST_LISTED))], 0, 1)
    assert "no further listed strike" in err.value.message.what_happened
    assert "Leg 1" in err.value.message.what_happened


def test_ac_2_typed_zero_negative_text_off_tick_and_three_decimals_are_refused_with_four_parts_and_keep_the_price(cat):
    """REQ-077 AC-2 (attack 1): 0, -5, 'abc', 81.32, 81.305 and NaN are refused with the four-part catalogue error
    naming leg 1 and the 0.05 tick; the legs as sent keep their previous price and mark."""
    legs = condor()
    before = [(x.leg.entry_price, x.typed) for x in legs]
    for bad in (D("0"), -5, "abc", D("81.32"), D("81.305"), D("NaN"), D("-5"), 81.3, "-5", "0", "0.00", "81.32",
                "81.305", "1e2", " 5", "NaN", "", "٨١", None):
        with pytest.raises(LegEditRefused) as err:
            leg_edit.set_typed_price(cat, NIFTY, legs, 0, bad)
        parts = err.value.message
        assert err.value.template == "leg_edit_price_not_tick"
        assert "Leg 1" in parts.what_happened and "0.05" in parts.what_happened
        assert all(getattr(parts, name) for name in ("what_happened", "impact", "what_is_blocked", "next_action"))
    assert [(x.leg.entry_price, x.typed) for x in legs] == before
    ok = leg_edit.set_typed_price(cat, NIFTY, legs, 0, D("81.30"))
    assert ok[0].leg.entry_price == D("81.30") and ok[0].typed and [x.typed for x in ok[1:]] == [False] * 3


def test_ac_2_a_typed_price_is_stored_and_echoed_with_two_decimals(cat):
    """REQ-077 AC-2: the text "81.3" (and the Decimal 81.3) is stored as the 2-decimal 81.30, never "81.3"."""
    for typed in ("81.3", D("81.3"), "81.30"):
        out = leg_edit.set_typed_price(cat, NIFTY, condor(), 0, typed)
        assert str(out[0].leg.entry_price) == "81.30"


# ---- REQ-078 (W-158; ADR-186): Shift / Width / Hedge on the real instrument file ---------------------------------

def max_loss_of(legs) -> D:
    """The engine's max loss of the legs (a positive amount)."""
    return strategy_metrics(Strategy(tuple(x.leg for x in legs))).max_loss


def test_core_proof_shift_width_hedge_on_real_instrument_file(cat):
    """REQ-078 AC-1 (core): the fixture's own NIFTY listing of 2026-10-06 runs 20800..25800 in steps of 50 (strike gap
    50). The condor() is BUY 22800 PE @42.50, SELL 23000 PE @86.00, SELL 23400 CE @91.50, BUY 23600 CE @44.00, 65 units.
    HAND, written before the code:
      credit per unit = 86.00 + 91.50 - 42.50 - 44.00 = 91.00; both wings are 200 wide, so the worst case is a wing
      fully in the money: loss per unit = 200 - 91.00 = 109.00, x 65 = 7,085.00.
      Shift +1  -> 22850 / 23050 / 23450 / 23650: wings still 200 -> max loss 7,085.00.
      Width +1  -> puts one step down, calls one step up: 22750 / 22950 / 23450 / 23650: wings still 200 -> 7,085.00;
                   the width (lowest call - highest put) goes 23400 - 23000 = 400 to 23450 - 22950 = 500.
      Hedge +1  -> both hedges (the two BUY legs) one step out: BUY 22750 PE and BUY 23650 CE: wings 250 -> loss per
                   unit = 250 - 91.00 = 159.00, x 65 = 10,335.00.
    Every strike must be in the fixture's listing and unexpired; the moved legs keep side, lots, expiry and type."""
    start = condor()
    listed = set(LISTING.strikes(NIFTY, EXPIRY, Instrument.CE)) & set(LISTING.strikes(NIFTY, EXPIRY, Instrument.PE))
    assert (min(listed), max(listed)) == (FIRST_LISTED, LAST_LISTED) and cat.strike_gap(NIFTY, EXPIRY) == D("50")
    assert max_loss_of(start) == D("7085.00")
    protective = frozenset({0, 3})
    cases = [("shift", leg_edit.shift(LISTING, NIFTY, start, 1), ["22850", "23050", "23450", "23650"], "7085.00"),
             ("width", leg_edit.width(LISTING, NIFTY, start, 1), ["22750", "22950", "23450", "23650"], "7085.00"),
             ("hedge", leg_edit.hedge(LISTING, NIFTY, start, protective, 1), ["22750", "23000", "23400", "23650"],
              "10335.00")]
    for name, result, expected, loss in cases:
        assert strikes(result.legs) == [D(s) for s in expected], name
        assert all(x.leg.strike in listed for x in result.legs), name
        assert max_loss_of(result.legs) == D(loss), name
        assert [(x.leg.action, x.leg.instrument, x.leg.expiry, x.lots, x.leg.quantity) for x in result.legs] == [
            (x.leg.action, x.leg.instrument, x.leg.expiry, x.lots, x.leg.quantity) for x in start], name
    assert strikes(start) == [D("22800"), D("23000"), D("23400"), D("23600")]  # the input is never changed
    assert cases[0][1].moved == frozenset({0, 1, 2, 3}) and cases[2][1].moved == frozenset({0, 3})


def test_attack_1_a_shift_landing_on_an_unlisted_or_expired_strike_refuses_the_whole_move_naming_the_leg(cat):
    """REQ-078 AC-6: on 2026-09-29 the far strikes jump 19500 -> 20800, so a Shift -1 of a leg at 20800 would land on
    20750 (not listed): nothing moves, even the leg that would have landed fine, and the text names that leg."""
    legs = [one(Instrument.CE, "23000", EARLY_EXPIRY), one(Instrument.PE, "20800", EARLY_EXPIRY)]
    with pytest.raises(LegEditRefused) as err:
        leg_edit.shift(LISTING, NIFTY, legs, -1)
    assert err.value.template == "leg_edit_landing_not_listed"
    assert err.value.message.what_happened == "No 20,750 PE is listed for 29 Sep 2026, so leg 2 cannot move there."
    assert strikes(legs) == [D("23000"), D("20800")]  # nothing changed
    after = Listing(CAT, datetime.date(2026, 10, 7))  # the 2026-10-06 expiry has passed
    with pytest.raises(LegEditRefused) as err:
        leg_edit.shift(after, NIFTY, condor(), 1)
    assert err.value.template == "leg_edit_strike_not_listed" and "Leg 1" in err.value.message.what_happened
    with pytest.raises(LegEditRefused) as err:
        leg_edit.shift(LISTING, NIFTY, [one(Instrument.FUT, None)], 1)
    assert err.value.template == "leg_edit_shift_needs_option_leg"


def test_ac_3_shift_moves_every_option_leg_and_no_futures_leg_and_a_negative_shift_goes_down(cat):
    legs = [*condor(), one(Instrument.FUT, None, price="23100")]
    up = leg_edit.shift(LISTING, NIFTY, legs, 1)
    assert strikes(up.legs) == [D("22850"), D("23050"), D("23450"), D("23650"), None]
    assert up.moved == frozenset({0, 1, 2, 3})
    down = leg_edit.shift(LISTING, NIFTY, legs, -1)
    assert strikes(down.legs) == [D("22750"), D("22950"), D("23350"), D("23550"), None]


def test_ac_4_width_moves_both_sides_with_no_spot_and_never_goes_below_zero(cat):
    """A strangle SELL 22900 PE / SELL 23100 CE has width 200: Width +1 -> 22850 / 23150 (300), Width -1 -> 22950 /
    23050 (100). A straddle (width 0) and a width of one step refuse -1 (it would cross); +1 on the straddle works."""
    strangle = [one(Instrument.PE, "22900", action=Action.SELL), one(Instrument.CE, "23100", action=Action.SELL)]
    assert strikes(leg_edit.width(LISTING, NIFTY, strangle, 1).legs) == [D("22850"), D("23150")]
    assert strikes(leg_edit.width(LISTING, NIFTY, strangle, -1).legs) == [D("22950"), D("23050")]
    straddle = [one(Instrument.PE, "23000", action=Action.SELL), one(Instrument.CE, "23000", action=Action.SELL)]
    assert strikes(leg_edit.width(LISTING, NIFTY, straddle, 1).legs) == [D("22950"), D("23050")]
    with pytest.raises(LegEditRefused) as err:  # width 0: nothing left to take away
        leg_edit.width(LISTING, NIFTY, straddle, -1)
    assert err.value.template == "leg_edit_width_below_zero"
    with pytest.raises(LegEditRefused) as err:
        leg_edit.width(LISTING, NIFTY, [one(Instrument.CE, "23000")], 1)
    assert err.value.template == "leg_edit_width_not_applicable"


def one_step_strangle() -> list[EditLeg]:
    return [one(Instrument.PE, "22950", action=Action.SELL), one(Instrument.CE, "23000", action=Action.SELL)]


def test_adr_186_5_width_last_step_no_spot_moves_the_call_side():
    """PROOF (core): strangle 22,950 PE / 23,000 CE (width 50 = one step), Width -1: half the change is under a step, so
    ONE side moves by the whole change; with no live price the CALL moves -> 22,950 PE / 22,950 CE (ADR-186 example)."""
    legs = one_step_strangle()
    moved = leg_edit.width(LISTING, NIFTY, legs, -1)
    assert strikes(moved.legs) == [D("22950"), D("22950")] and moved.moved == frozenset({1})
    assert strikes(legs) == [D("22950"), D("23000")]  # the input is never changed
    assert strikes(leg_edit.width(LISTING, NIFTY, legs, -1, None).legs) == [D("22950"), D("22950")]


def test_adr_186_5_width_last_step_moves_the_side_nearer_spot_and_ties_go_to_the_call():
    legs = one_step_strangle()
    near_call = leg_edit.width(LISTING, NIFTY, legs, -1, D("22990"))
    assert strikes(near_call.legs) == [D("22950"), D("22950")] and near_call.moved == frozenset({1})
    near_put = leg_edit.width(LISTING, NIFTY, legs, -1, D("22955"))
    assert strikes(near_put.legs) == [D("23000"), D("23000")] and near_put.moved == frozenset({0})
    tie = leg_edit.width(LISTING, NIFTY, legs, -1, D("22975"))  # 25 from both sides: the call side, as with no price
    assert strikes(tie.legs) == [D("22950"), D("22950")]
    two = [one(Instrument.PE, "22900", action=Action.SELL), one(Instrument.CE, "23000", action=Action.SELL)]
    # width 100 = two steps: half the change is a whole step, so both sides move whatever the price says
    assert strikes(leg_edit.width(LISTING, NIFTY, two, -1, D("22905")).legs) == [D("22950"), D("22950")]


def test_adr_186_5_width_last_step_clamps_at_zero_and_a_zero_width_refuses_minus_one():
    """Width never goes below 0: 75 wide (a typed gap, 1.5 steps) is not a case here; the clamp is for one step. A
    straddle (width 0) refuses -1 whatever the price; +1 on one step works both sides."""
    straddle = [one(Instrument.PE, "23000", action=Action.SELL), one(Instrument.CE, "23000", action=Action.SELL)]
    for spot in (None, D("23000"), D("22000")):
        with pytest.raises(LegEditRefused) as err:
            leg_edit.width(LISTING, NIFTY, straddle, -1, spot)
        assert err.value.template == "leg_edit_width_below_zero"
    assert strikes(leg_edit.width(LISTING, NIFTY, one_step_strangle(), 1, D("22990")).legs) == [D("22900"), D("23050")]


def test_minor_1_a_calendar_moves_each_leg_by_its_own_expiry_gap():
    """REQ-078 AC-3: 'the strike gap read from the instrument file for that expiry'. A listing where 2026-09-29 lists
    only every 100 (the real rows with the odd 50s removed) and 2026-10-06 every 50: Shift +1 moves the near leg 100 and
    the far leg 50, and the Shift total's step is the nearest expiry's."""
    thinned = Catalogue()
    thinned.load([r for r in parse_instruments_csv(FIXTURE)
                  if not (r.contract.name == NIFTY and r.contract.expiry == EARLY_EXPIRY and r.contract.strike % 100)])
    listing = Listing(thinned, TODAY)
    assert (thinned.strike_gap(NIFTY, EARLY_EXPIRY), thinned.strike_gap(NIFTY, EXPIRY)) == (D("100"), D("50"))
    legs = [one(Instrument.CE, "23000", EARLY_EXPIRY, Action.SELL), one(Instrument.CE, "23000", EXPIRY)]
    assert strikes(leg_edit.shift(listing, NIFTY, legs, 1).legs) == [D("23100"), D("23050")]
    assert strikes(leg_edit.shift(listing, NIFTY, legs, -1).legs) == [D("22900"), D("22950")]
    assert leg_edit.shift_step(listing, NIFTY, legs) == D("100")
    assert leg_edit.shift_step(listing, NIFTY, legs[::-1]) == D("100")  # the nearest expiry, whatever the leg order


def test_attack_3_hedge_moves_only_the_marked_legs_refuses_one_step_and_a_six_leg_set(cat):
    """AC-5: Hedge +1 on the condor moves only the two BUY (marked) legs; Hedge -1 at 50-point hedges refuses; a 6-leg
    set and an empty mark set refuse; a vertical spread moves its one hedge leg one step."""
    protective = frozenset({0, 3})
    plus = leg_edit.hedge(LISTING, NIFTY, condor(), protective, 1)
    assert strikes(plus.legs) == [D("22750"), D("23000"), D("23400"), D("23650")] and plus.moved == protective
    tight = [one(Instrument.PE, "22950"), one(Instrument.PE, "23000", action=Action.SELL),
             one(Instrument.CE, "23400", action=Action.SELL), one(Instrument.CE, "23450")]
    with pytest.raises(LegEditRefused) as err:
        leg_edit.hedge(LISTING, NIFTY, tight, protective, -1)
    assert err.value.template == "leg_edit_hedge_below_minimum" and "Leg 1" in err.value.message.what_happened
    six = [*condor(), one(Instrument.CE, "23800"), one(Instrument.CE, "23900", action=Action.SELL)]
    for bad, marks in ((six, protective), (condor(), frozenset())):
        with pytest.raises(LegEditRefused) as err:
            leg_edit.hedge(LISTING, NIFTY, bad, marks, 1)
        assert err.value.template == "leg_edit_hedge_not_applicable"
    spread = [one(Instrument.CE, "23000", action=Action.SELL), one(Instrument.CE, "23200")]
    assert strikes(leg_edit.hedge(LISTING, NIFTY, spread, frozenset({1}), 1).legs) == [D("23000"), D("23250")]
    assert strikes(leg_edit.hedge(LISTING, NIFTY, spread, frozenset({1}), -1).legs) == [D("23000"), D("23150")]


def test_adr_186_1_unequal_hedges_even_out_only_one_side_moves(cat):
    """put hedge 300 (BUY 22500 / SELL 22800 PE), call hedge 200 (SELL 23200 / BUY 23400 CE). Hedge +1: only the call
    hedge goes out to 300 -> 23500, puts untouched; again: both 350. Hedge -1: only the FARTHER (put) hedge comes in to
    200 -> 22600, calls untouched."""
    unequal = [one(Instrument.PE, "22500"), one(Instrument.PE, "22800", action=Action.SELL),
               one(Instrument.CE, "23200", action=Action.SELL), one(Instrument.CE, "23400")]
    marks = frozenset({0, 3})
    first = leg_edit.hedge(LISTING, NIFTY, unequal, marks, 1)
    assert strikes(first.legs) == [D("22500"), D("22800"), D("23200"), D("23500")] and first.moved == frozenset({3})
    second = leg_edit.hedge(LISTING, NIFTY, first.legs, marks, 1)
    assert strikes(second.legs) == [D("22450"), D("22800"), D("23200"), D("23550")] and second.moved == marks
    inward = leg_edit.hedge(LISTING, NIFTY, unequal, marks, -1)
    assert strikes(inward.legs) == [D("22600"), D("22800"), D("23200"), D("23400")] and inward.moved == frozenset({0})


def test_ac_7_a_move_changes_no_side_lots_expiry_type_or_leg_count(cat):
    legs = condor()
    for result in (leg_edit.shift(LISTING, NIFTY, legs, 1), leg_edit.width(LISTING, NIFTY, legs, -1),
                   leg_edit.hedge(LISTING, NIFTY, legs, frozenset({0, 3}), 1)):
        assert len(result.legs) == len(legs)
        for before, after in zip(legs, result.legs, strict=True):
            assert (before.leg.action, before.leg.instrument, before.leg.expiry, before.lots, before.base_lots,
                    before.leg.quantity) == (after.leg.action, after.leg.instrument, after.leg.expiry, after.lots,
                                             after.base_lots, after.leg.quantity)


def test_ac_8_a_moved_leg_loses_its_typed_mark_an_unmoved_one_keeps_it(cat):
    legs = leg_edit.set_typed_price(cat, NIFTY, condor(), 0, D("40.00"))
    legs = leg_edit.set_typed_price(cat, NIFTY, legs, 1, D("80.00"))
    out = leg_edit.hedge(LISTING, NIFTY, legs, frozenset({0, 3}), 1).legs
    assert [x.typed for x in out] == [False, True, False, False] and out[1].leg.entry_price == D("80.00")
