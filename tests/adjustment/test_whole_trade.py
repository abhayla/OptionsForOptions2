# ruff: noqa: PLR2004 - exact expected amounts are the assertions
"""REQ-155 AC-2, AC-3 (F-74): the whole-trade After = open legs at expiry + booked P&L, less each charge line once.

Expected values never come from the code under test: the scenario library's ``expected.at_expiry_whole_trade`` is the
generator's intrinsic-value hand path (tests/adjust_scenarios_gen.py), and the AC-2 / AC-3 cases are arithmetic on
those hand values.
"""
from __future__ import annotations

import datetime
import json
from decimal import Decimal as D
from pathlib import Path

import pytest
from ofo.engine.black_scholes import probability_below
from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.metrics import UNLIMITED, MultiExpiryError, breakevens_with_shift, strategy_metrics
from ofo.engine.pop import Why
from ofo.engine.strategy import Strategy
from ofo.engine.whole_trade import whole_trade_after
from ofo.money import HUNDREDTH

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "adjust_scenarios"
IDS = sorted(p.stem for p in FIX.glob("ADJ-*.json"))
ZERO = D(0)


def _load(sid: str) -> dict:
    return json.loads((FIX / f"{sid}.json").read_text(encoding="utf-8"))


def _strategy(sc: dict) -> Strategy:
    return Strategy(tuple(
        Leg(Action(x["side"]), Instrument(x["type"]), None if x["strike"] is None else D(x["strike"]),
            datetime.date.fromisoformat(x["expiry"]), x["quantity"], D(x["entry"])) for x in sc["position"]["legs"]))


def _after(strategy: Strategy, booked=ZERO, paid=ZERO, adjustment=ZERO, exits=ZERO):
    return whole_trade_after(strategy, booked_pnl=booked, paid_charges=paid, adjustment_charges=adjustment,
                             open_exit_charges=exits)


def _text(value) -> str | D:
    return "UNLIMITED" if value is UNLIMITED else value


def _matches(value, hand: str) -> bool:
    return _text(value) == hand or (value is not UNLIMITED and hand != "UNLIMITED" and value == D(hand))


def test_core_adj13_gross_whole_trade_equals_the_hand_values_to_the_paisa():
    """Core proof: ADJ-13 (booked +962 from an earlier roll) -> 5,141.50 / 20,858.50 / 22,860.45 and 23,489.55."""
    sc = _load("ADJ-13")
    w = _after(_strategy(sc), booked=D(sc["position"]["booked_pnl"]))
    assert w.gross.max_profit == D("5141.5") and w.gross.max_loss == D("20858.5")
    assert w.gross.breakevens == (D("22860.45"), D("23489.55"))
    assert w.gross.loss_regions == ((None, D("22860.45")), (D("23489.55"), None))
    open_alone = strategy_metrics(_strategy(sc))
    assert open_alone.max_loss - w.gross.max_loss == D("962")  # booked P&L is part of the After (F-74)


def test_ac2_booked_plus_1200_lowers_max_loss_by_exactly_1200():
    """AC-2 example: a condor that booked +1,200 shows an After max loss 1,200 smaller than its open legs alone."""
    s = _strategy(_load("ADJ-23"))  # open legs alone: max profit 7,026.50, max loss 18,973.50 (hand values)
    alone, booked = _after(s), _after(s, booked=D("1200"))
    assert alone.gross.max_loss == D("18973.5") and booked.gross.max_loss == D("17773.5")
    assert booked.gross.max_profit == D("8226.5")
    assert booked.gross.breakevens == breakevens_with_shift(s, D("1200"))
    assert booked.gross.breakevens[0] < alone.gross.breakevens[0]  # the lower breakeven moves further away


def test_ac3_each_charge_line_is_kept_apart_and_subtracted_exactly_once():
    """AC-3: paid 150.25 + adjustment 92.40 + open exits 60.10 = 302.75 off max profit and onto max loss, once."""
    s = _strategy(_load("ADJ-13"))
    w = _after(s, booked=D("962"), paid=D("150.25"), adjustment=D("92.40"), exits=D("60.10"))
    assert (w.paid_charges, w.adjustment_charges, w.open_exit_charges) == (D("150.25"), D("92.40"), D("60.10"))
    assert w.total_charges == D("302.75")
    assert w.gross.max_profit == D("5141.5")  # gross is before any charge
    assert w.after_charges.max_profit == D("4838.75") and w.after_charges.max_loss == D("21161.25")
    # (5141.50 - 302.75) / 130 = 37.2211538... points inside each short: 22862.78 (rounded) and 23487.22
    assert w.after_charges.breakevens == (D("22862.78"), D("23487.22"))
    base = {"paid": D("150.25"), "adjustment": D("92.40"), "exits": D("60.10")}
    for field, amount in base.items():  # +1 rupee on ONE line moves max loss by exactly 1 (never twice, never 0)
        bumped = _after(s, booked=D("962"), **{**base, field: amount + 1})
        assert bumped.after_charges.max_loss - w.after_charges.max_loss == D(1), field
        assert w.after_charges.max_profit - bumped.after_charges.max_profit == D(1), field


@pytest.mark.parametrize("sid", IDS)
def test_ac2_every_scenario_whole_trade_matches_the_hand_values(sid):
    """Every scenario with ``exact`` true: gross max profit, max loss and breakevens equal the hand values; a scenario
    with legs on more than one expiry raises MultiExpiryError (attack 5), never a silent answer."""
    sc = _load(sid)
    hand = sc["expected"]["at_expiry_whole_trade"]
    s = _strategy(sc)
    booked = D(sc["position"]["booked_pnl"])
    if not hand["exact"]:
        with pytest.raises(MultiExpiryError):
            _after(s, booked=booked)
        return
    w = _after(s, booked=booked)
    assert _matches(w.gross.max_profit, hand["max_profit"]), (w.gross.max_profit, hand)
    assert _matches(w.gross.max_loss, hand["max_loss"]), (w.gross.max_loss, hand)
    assert list(w.gross.breakevens) == [D(b) for b in hand["breakevens"]]


def test_the_scenario_loop_covers_both_answer_states():
    states = {_load(sid)["expected"]["at_expiry_whole_trade"]["exact"] for sid in IDS}
    assert states == {True, False}
    assert len(IDS) >= 40


def test_attack2_unlimited_max_loss_stays_unlimited_with_a_booked_shift():
    """A naked sold call: max loss UNLIMITED before and after +5,000 booked and charges."""
    s = Strategy((Leg(Action.SELL, Instrument.CE, D("23500"), datetime.date(2026, 11, 3), 65, D("40.00")),))
    w = _after(s, booked=D("5000"), paid=D("40"), adjustment=D("30"), exits=D("20"))
    assert w.gross.max_loss is UNLIMITED and w.after_charges.max_loss is UNLIMITED
    assert w.gross.max_profit == D("7600")  # 40 x 65 + 5,000
    assert w.gross.breakevens == (D("23616.92"),)  # 23500 + 7600/65 = 23616.923... rounded half-even


def test_attack3_booked_loss_larger_than_open_max_profit_gives_negative_max_profit_no_sign_flip():
    s = _strategy(_load("ADJ-23"))  # open max profit 7,026.50
    w = _after(s, booked=D("-10000"))
    assert w.gross.max_profit == D("-2973.5")
    assert w.gross.max_loss == D("28973.5")
    assert w.gross.breakevens == ()
    assert w.gross.loss_regions == ((None, None),)


def test_attack4_zero_shift_and_zero_charges_equal_strategy_metrics():
    for sid in ("ADJ-01", "ADJ-23", "ADJ-35", "ADJ-40"):
        s = _strategy(_load(sid))
        m, w = strategy_metrics(s), _after(s)
        assert (w.gross.max_profit, w.gross.max_loss, w.gross.breakevens, w.gross.loss_regions) == (
            m.max_profit, m.max_loss, m.breakevens, m.loss_regions)
        assert w.after_charges == w.gross


def test_ac4_after_charges_levels_are_on_the_paise_step_adj23():
    sc = _load("ADJ-23")
    w = _after(_strategy(sc), exits=D(sc["position"]["charges_round_trip"]))
    assert w.after_charges.breakevens == (D("22547.49"), D("23502.51"))
    assert all(b == b.quantize(HUNDREDTH) for b in w.after_charges.breakevens)


@pytest.mark.parametrize(("kwargs", "name"), [
    ({"paid": D("-1")}, "paid_charges"),
    ({"adjustment": D("-0.01")}, "adjustment_charges"),
    ({"exits": 1.5}, "open_exit_charges"),
    ({"booked": D("NaN")}, "booked_pnl"),
    ({"booked": 962}, "booked_pnl"),
])
def test_bad_amounts_are_refused_by_name(kwargs, name):
    with pytest.raises(ValueError, match=name):
        _after(_strategy(_load("ADJ-13")), **kwargs)


@pytest.mark.parametrize(("kwargs", "name"), [
    ({"booked": D("962.005")}, "booked_pnl"),
    ({"paid": D("0.001")}, "paid_charges"),
    ({"adjustment": D("92.405")}, "adjustment_charges"),
    ({"exits": D("60.1000001")}, "open_exit_charges"),
])
def test_amounts_finer_than_paise_are_refused_by_name(kwargs, name):
    with pytest.raises(ValueError, match=name):
        _after(_strategy(_load("ADJ-13")), **kwargs)


ADJ13_FORWARD, ADJ13_YEARS, ADJ13_VOL = D("23250"), D(4) / D(365), D("0.13")  # ADJ-13 market: spot, dte, atm_iv


def _adj13_pop(booked: D, paid=ZERO, adjustment=ZERO, exits=ZERO):
    return whole_trade_after(_strategy(_load("ADJ-13")), booked_pnl=booked, paid_charges=paid,
                             adjustment_charges=adjustment, open_exit_charges=exits,
                             forward=ADJ13_FORWARD, years=ADJ13_YEARS, vol=ADJ13_VOL)


def test_ac2_pop_includes_booked_pnl_and_charges():
    """AC-2: booked +962 widens the profit zone, so POP rises; charges narrow it, so POP falls. The figure equals the
    lognormal mass between the whole trade's own after-charges breakevens (probability_below at each level)."""
    without, booked = _adj13_pop(ZERO), _adj13_pop(D("962"))
    charged = _adj13_pop(D("962"), paid=D("150.25"), adjustment=D("92.40"), exits=D("60.10"))
    assert without.pop_unavailable is None and booked.pop_unavailable is None
    assert ZERO < without.pop < booked.pop < D(1)
    assert charged.pop < booked.pop
    lo, hi = charged.after_charges.breakevens
    between = (probability_below(hi, ADJ13_FORWARD, ADJ13_YEARS, ADJ13_VOL)
               - probability_below(lo, ADJ13_FORWARD, ADJ13_YEARS, ADJ13_VOL))
    assert charged.pop == between


def test_ac2_pop_is_zero_when_the_booked_loss_exceeds_what_the_open_legs_can_make():
    w = _adj13_pop(D("-10000"))
    assert w.pop == ZERO and w.pop_unavailable is None


@pytest.mark.parametrize(("forward", "years", "vol", "why"), [
    (ADJ13_FORWARD, ADJ13_YEARS, None, Why.NO_VOLATILITY),
    (ADJ13_FORWARD, None, ADJ13_VOL, Why.NO_VOLATILITY),
    (None, ADJ13_YEARS, ADJ13_VOL, Why.NO_FORWARD),
])
def test_ac4_pop_missing_input_gives_a_named_reason_never_an_exception_or_a_blank(forward, years, vol, why):
    w = whole_trade_after(_strategy(_load("ADJ-13")), booked_pnl=D("962"), paid_charges=ZERO, adjustment_charges=ZERO,
                          open_exit_charges=ZERO, forward=forward, years=years, vol=vol)
    assert w.pop is None and w.pop_unavailable is why
    assert w.gross.max_loss == D("20858.5")  # the other figures still come back
