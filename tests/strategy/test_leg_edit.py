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
from ofo.strategy.leg_edit import EditLeg, LegEditRefused
from ofo.strategy.matching import CUSTOM_STRATEGY, Custom, match, protective_keys
from ofo.strategy.loader import load_templates

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "instruments" / "instruments_slice.csv"
EXPIRY = datetime.date(2026, 10, 6)
EARLY_EXPIRY = datetime.date(2026, 9, 29)
TODAY = datetime.date(2026, 9, 28)  # before both expiries
LOT = 65
NIFTY = "NIFTY"
FIRST_LISTED, LAST_LISTED = D("20800"), D("25800")
INCLUDED_AFTER_UNTICK = 3
SENSEX_LOT = 20


@pytest.fixture(scope="module")
def cat() -> Catalogue:
    c = Catalogue()
    c.load(parse_instruments_csv(FIXTURE))
    return c


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
    result = leg_edit.step_strike(cat, NIFTY, legs, 0, 1, TODAY)
    assert strikes(result.legs) == [D("23050"), D("22900")]
    assert result.moved == frozenset({0})  # AC-2: the other leg is not marked for a new capture
    assert result.legs[1] == legs[1]  # and keeps its planned entry untouched
    assert legs[0].leg.strike == D("23000")  # the input is never changed
    last = [one(Instrument.CE, str(LAST_LISTED))]
    with pytest.raises(LegEditRefused) as err:
        leg_edit.step_strike(cat, NIFTY, last, 0, 1, TODAY)
    assert err.value.template == "leg_edit_no_further_strike"


def test_ac_1_both_edges_futures_and_unlisted_are_refused(cat):
    """REQ-076 AC-1: no step below the first listed strike; a futures leg has no stepper; an unlisted strike is refused
    (never rounded to a neighbour); a past expiry lists nothing."""
    first = [one(Instrument.PE, str(FIRST_LISTED))]
    with pytest.raises(LegEditRefused) as err:
        leg_edit.step_strike(cat, NIFTY, first, 0, -1, TODAY)
    assert err.value.template == "leg_edit_no_further_strike"
    assert leg_edit.step_strike(cat, NIFTY, first, 0, 1, TODAY).legs[0].leg.strike == D("20850")
    with pytest.raises(LegEditRefused) as err:
        leg_edit.step_strike(cat, NIFTY, [one(Instrument.FUT, None)], 0, 1, TODAY)
    assert err.value.template == "leg_edit_futures_no_stepper"
    with pytest.raises(LegEditRefused) as err:
        leg_edit.step_strike(cat, NIFTY, [one(Instrument.CE, "23010")], 0, 1, TODAY)
    assert err.value.template == "leg_edit_strike_not_listed"
    with pytest.raises(LegEditRefused) as err:
        leg_edit.step_strike(cat, NIFTY, [one(Instrument.CE, "23000")], 0, 1, EXPIRY + datetime.timedelta(days=1))
    assert err.value.template == "leg_edit_strike_not_listed"


def test_ac_1_far_from_the_money_the_step_follows_the_listed_jump(cat):
    """REQ-076 AC-1: where the list jumps (the file lists 19500 then 20800 on 2026-09-29) + goes to the next LISTED
    strike, not strike + 50; SENSEX steps by its own 100."""
    far = [one(Instrument.CE, "19500", expiry=EARLY_EXPIRY)]
    jumped = leg_edit.step_strike(cat, NIFTY, far, 0, 1, TODAY)
    assert strikes(jumped.legs) == [D("20800")]
    back = leg_edit.step_strike(cat, NIFTY, jumped.legs, 0, -1, TODAY)
    assert strikes(back.legs) == [D("19500")]
    sensex_expiry = datetime.date(2026, 10, 8)
    grid = leg_edit.listed_strikes(cat, "SENSEX", sensex_expiry, Instrument.CE, TODAY)
    legs = [EditLeg(Leg(Action.BUY, Instrument.CE, grid[10], sensex_expiry, SENSEX_LOT, D("10")), 1, 1)]
    assert leg_edit.step_strike(cat, "SENSEX", legs, 0, 1, TODAY).legs[0].leg.strike == grid[11]
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
    assert len(marks) == 2
    changed = [*legs[:3], Leg(Action.BUY, Instrument.PE, D("23200"), EXPIRY, LOT, D("50"))]
    again = match(changed, spot=spot, strike_gap=gap, templates=load_templates())
    assert isinstance(again, Custom) and CUSTOM_STRATEGY == "Custom Strategy"
    assert legs[3].strike == D("23400")  # naming never changed a leg


def test_ac_6_a_stepped_leg_is_re_captured_and_a_typed_price_is_a_tick_multiple(cat):
    """REQ-076 AC-2 / REQ-077 AC-2: with_entries replaces the stepped leg's entry only and clears the typed mark; a
    typed price must be a positive multiple of the file's 0.05 tick."""
    legs = condor()
    moved = leg_edit.step_strike(cat, NIFTY, legs, 1, 1, TODAY)
    fresh = leg_edit.with_entries(moved.legs, {1: D("62.10")})
    assert [x.leg.entry_price for x in fresh] == [D("42.50"), D("62.10"), D("91.50"), D("44.00")]
    ok = leg_edit.set_typed_price(cat, NIFTY, legs, 1, D("81.35"))
    assert ok[1].leg.entry_price == D("81.35") and ok[1].typed
    assert not leg_edit.with_entries(ok, {1: D("90.00")})[1].typed
    for bad in (D("81.32"), D("0"), D("-0.05")):
        with pytest.raises(LegEditRefused) as err:
            leg_edit.set_typed_price(cat, NIFTY, legs, 1, bad)
        assert err.value.template == "leg_edit_price_not_tick"


def test_refusals_are_user_facing_catalogue_text(cat):
    """Every refusal renders from the error catalogue (no ad-hoc string) and names the leg."""
    with pytest.raises(LegEditRefused) as err:
        leg_edit.step_strike(cat, NIFTY, [one(Instrument.CE, str(LAST_LISTED))], 0, 1, TODAY)
    assert "no further listed strike" in err.value.message.what_happened
    assert "Leg 1" in err.value.message.what_happened
