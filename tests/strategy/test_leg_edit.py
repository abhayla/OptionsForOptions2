"""W-126 (REQ-076, REQ-077, REQ-078): the pure leg-edit functions on the REAL instrument-list fixture.

Core proof (REQ-078 AC-1, builder part): a NIFTY iron condor on the fixture's 2026-10-06 expiry (real strikes, 65-unit
lot) moved once each by Shift +1, Width +1 and Hedge +1. Every expected strike and max loss below is a hand
computation written before the code; none was copied from the code's output.

Hand computation (per unit, then x 65):
  start      BUY 22800 PE @42.50, SELL 23000 PE @86.00, SELL 23400 CE @91.50, BUY 23600 CE @44.00
             credit 86 + 91.5 - 42.5 - 44 = 91.00; wings 200; max loss (200 - 91) x 65 = 7,085.00
  Shift +1   every option leg +50 -> 22850 / 23050 / 23450 / 23650; re-captured prices 45 / 90 / 88 / 41
             credit 90 + 88 - 45 - 41 = 92; wings 200; max loss (200 - 92) x 65 = 7,020.00
  Width +1   calls +50, puts -50 -> 22750 / 22950 / 23450 / 23650; re-captured 40 / 83 / 88 / 41
             credit 83 + 88 - 40 - 41 = 90; wings 200; max loss (200 - 90) x 65 = 7,150.00
  Hedge +1   only the long wings move: 22800 -> 22750, 23600 -> 23650; shorts keep 86.00 / 91.50; new wings @40 / 41
             credit 86 + 91.5 - 40 - 41 = 96.50; wings 250; max loss (250 - 96.5) x 65 = 9,977.50
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from pathlib import Path

import pytest

from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.engine.metrics import strategy_metrics
from ofo.instruments import Catalogue, parse_instruments_csv
from ofo.strategy import leg_edit
from ofo.strategy.leg_edit import EditLeg, LegEditRefused

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "instruments" / "instruments_slice.csv"
EXPIRY = datetime.date(2026, 10, 6)
LOT = 65
NIFTY = "NIFTY"


@pytest.fixture(scope="module")
def cat() -> Catalogue:
    c = Catalogue()
    c.load(parse_instruments_csv(FIXTURE))
    return c


def condor() -> list[EditLeg]:
    rows = [(Action.BUY, Instrument.PE, "22800", "42.50"), (Action.SELL, Instrument.PE, "23000", "86.00"),
            (Action.SELL, Instrument.CE, "23400", "91.50"), (Action.BUY, Instrument.CE, "23600", "44.00")]
    return [EditLeg(Leg(a, i, D(s), EXPIRY, LOT, D(p)), lots=1, base_lots=1) for a, i, s, p in rows]


PROTECTIVE = frozenset({0, 3})  # the two long wings (catalogue `protective: true` on iron_condor)


def strikes(legs) -> list[D]:
    return [x.leg.strike for x in legs]


def max_loss(legs) -> D:
    return strategy_metrics(Strategy(tuple(x.leg for x in legs))).max_loss


def priced(result: leg_edit.Moved, prices: dict[int, str]) -> list[EditLeg]:
    """What the route does: re-capture a planned entry for each moved leg (here a hand-typed table)."""
    assert set(prices) == set(result.moved)
    return leg_edit.with_entries(result.legs, {i: D(p) for i, p in prices.items()})


def test_core_proof_shift_width_hedge_on_real_instrument_file(cat):
    """REQ-078 AC-1 (builder part): the three moves, strikes and the engine's max loss equal the hand computation."""
    start = condor()
    assert max_loss(start) == D("7085.00")

    shifted = priced(leg_edit.shift(cat, NIFTY, start, 1), {0: "45", 1: "90", 2: "88", 3: "41"})
    assert strikes(shifted) == [D("22850"), D("23050"), D("23450"), D("23650")]
    assert max_loss(shifted) == D("7020.00")

    widened = priced(leg_edit.width(cat, NIFTY, start, 1), {0: "40", 1: "83", 2: "88", 3: "41"})
    assert strikes(widened) == [D("22750"), D("22950"), D("23450"), D("23650")]
    assert max_loss(widened) == D("7150.00")

    hedged = priced(leg_edit.hedge(cat, NIFTY, start, PROTECTIVE, 1), {0: "40", 3: "41"})
    assert strikes(hedged) == [D("22750"), D("23000"), D("23400"), D("23650")]
    assert max_loss(hedged) == D("9977.50")
    assert [x.leg.entry_price for x in hedged][1:3] == [D("86.00"), D("91.50")]  # unmoved legs keep their entry


def test_ac_078_3_shift_minus_one_and_futures_do_not_move(cat):
    """REQ-078 AC-3: -1 reverses; a futures leg does not move; the move changes no side, lots, expiry or type (AC-7)."""
    legs = condor() + [EditLeg(Leg(Action.BUY, Instrument.FUT, None, EXPIRY, LOT, D("23100.00")), 1, 1)]
    moved = leg_edit.shift(cat, NIFTY, legs, -1)
    assert strikes(moved.legs)[:4] == [D("22750"), D("22950"), D("23350"), D("23550")]
    assert moved.legs[4] == legs[4] and moved.moved == frozenset({0, 1, 2, 3})
    for before, after in zip(legs, moved.legs, strict=True):
        assert (before.leg.action, before.leg.instrument, before.leg.expiry, before.lots) == (
            after.leg.action, after.leg.instrument, after.leg.expiry, after.lots)


def test_ac_078_6_unlisted_landing_refuses_whole_move(cat):
    """REQ-078 AC-6: one leg landing on an unlisted strike refuses the whole move; the input is untouched."""
    legs = condor()
    legs[3] = EditLeg(Leg(Action.BUY, Instrument.CE, D("23610"), EXPIRY, LOT, D("44.00")), 1, 1)  # 23610 is off the grid
    with pytest.raises(LegEditRefused) as err:
        leg_edit.shift(cat, NIFTY, legs, 1)
    assert err.value.template == "leg_edit_strike_not_listed"
    assert strikes(legs) == [D("22800"), D("23000"), D("23400"), D("23610")]


def test_ac_078_4_width_never_below_zero(cat):
    """REQ-078 AC-4: Width -1 on a straddle (width 0) is refused; on the condor (width 400) it narrows by 100."""
    straddle = [EditLeg(Leg(Action.SELL, Instrument.CE, D("23000"), EXPIRY, LOT, D("100")), 1, 1),
                EditLeg(Leg(Action.SELL, Instrument.PE, D("23000"), EXPIRY, LOT, D("100")), 1, 1)]
    with pytest.raises(LegEditRefused) as err:
        leg_edit.width(cat, NIFTY, straddle, -1)
    assert err.value.template == "leg_edit_width_below_zero"
    narrowed = leg_edit.width(cat, NIFTY, condor(), -1)
    assert strikes(narrowed.legs) == [D("22850"), D("23050"), D("23350"), D("23550")]


def test_ac_078_5_hedge_minimum_one_step_and_leg_count(cat):
    """REQ-078 AC-5: Hedge -1 stops at one strike step; more than 4 legs is not computed."""
    tight = [EditLeg(Leg(Action.BUY, Instrument.PE, D("22950"), EXPIRY, LOT, D("50")), 1, 1),
             EditLeg(Leg(Action.SELL, Instrument.PE, D("23000"), EXPIRY, LOT, D("86")), 1, 1)]
    with pytest.raises(LegEditRefused) as err:
        leg_edit.hedge(cat, NIFTY, tight, frozenset({0}), -1)
    assert err.value.template == "leg_edit_hedge_below_minimum"
    six = condor() + condor()[:2]
    with pytest.raises(LegEditRefused) as err:
        leg_edit.hedge(cat, NIFTY, six, PROTECTIVE, 1)
    assert err.value.template == "leg_edit_hedge_not_applicable"


def test_ac_076_1_step_strike_uses_listed_strikes_and_edges(cat):
    """REQ-076 AC-1: the stepper walks the listed strikes (not strike + a constant); no step past the ends; no futures."""
    legs = condor()
    assert leg_edit.step_strike(cat, NIFTY, legs, 1, 1).legs[1].leg.strike == D("23050")
    first = min(c.strike for c in cat.contracts_for(NIFTY, EXPIRY, frozenset({"PE"})))
    edge = [EditLeg(Leg(Action.BUY, Instrument.PE, first, EXPIRY, LOT, D("1.00")), 1, 1)]
    with pytest.raises(LegEditRefused) as err:
        leg_edit.step_strike(cat, NIFTY, edge, 0, -1)
    assert err.value.template == "leg_edit_no_further_strike"
    fut = [EditLeg(Leg(Action.BUY, Instrument.FUT, None, EXPIRY, LOT, D("23100")), 1, 1)]
    with pytest.raises(LegEditRefused) as err:
        leg_edit.step_strike(cat, NIFTY, fut, 0, 1)
    assert err.value.template == "leg_edit_futures_no_stepper"


def test_ac_076_4_5_multiplier_is_base_lots_times_m_and_quantity_from_lot_size(cat):
    """REQ-076 AC-4/AC-5: lots = base x multiplier, back to 1 restores base; quantity = lots x the file's lot size."""
    legs = [EditLeg(x.leg, lots=2, base_lots=2) for x in condor()]
    three = leg_edit.apply_multiplier(cat, NIFTY, legs, 3)
    assert [x.lots for x in three] == [6] * 4 and [x.leg.quantity for x in three] == [6 * LOT] * 4
    assert [x.lots for x in leg_edit.apply_multiplier(cat, NIFTY, three, 1)] == [2] * 4
    for bad in (0, 51, True, 2.5):
        with pytest.raises(ValueError):
            leg_edit.apply_multiplier(cat, NIFTY, legs, bad)  # type: ignore[arg-type]


def test_ac_076_6_include_leg_flips_only_that_leg_and_unticked_leaves_the_engine_legs(cat):
    """REQ-076 AC-6: an unticked leg is absent from the engine's legs: unticking the bought wing makes max loss unlimited."""
    legs = leg_edit.include_leg(condor(), 3, False)
    assert [x.included for x in legs] == [True, True, True, False]
    included = leg_edit.included_legs(legs)
    assert len(included) == 3
    assert strategy_metrics(Strategy(tuple(x.leg for x in included))).max_loss is leg_edit.UNLIMITED


def test_ac_077_2_typed_price_must_be_a_positive_tick_multiple(cat):
    """REQ-077 AC-2: tick 0.05 from the file; 81.32 refused, 81.35 accepted and marked typed; 0 and negative refused."""
    legs = condor()
    ok = leg_edit.set_typed_price(cat, NIFTY, legs, 1, D("81.35"))
    assert ok[1].leg.entry_price == D("81.35") and ok[1].typed
    for bad in (D("81.32"), D("0"), D("-0.05")):
        with pytest.raises(LegEditRefused) as err:
            leg_edit.set_typed_price(cat, NIFTY, legs, 1, bad)
        assert err.value.template == "leg_edit_price_not_tick"
    assert legs[1].leg.entry_price == D("86.00") and not legs[1].typed


def test_ac_077_5_with_entries_replaces_typed_marks(cat):
    """REQ-077 AC-5 / REQ-078 AC-8: a re-captured entry replaces a typed price and clears the typed mark."""
    typed = leg_edit.set_typed_price(cat, NIFTY, condor(), 1, D("81.35"))
    again = leg_edit.with_entries(typed, {1: D("90.00")})
    assert again[1].leg.entry_price == D("90.00") and not again[1].typed


def test_refusals_are_user_facing_catalogue_text(cat):
    """Every refusal renders from the error catalogue (no ad-hoc string)."""
    with pytest.raises(LegEditRefused) as err:
        leg_edit.width(cat, NIFTY, condor()[:1], 1)
    assert err.value.message.what_happened == (
        "Width does not apply to this strategy.")
