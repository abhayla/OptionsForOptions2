# ruff: noqa: PLR2004 - exact expected values and loop sizes are the assertions
"""REQ-155 AC-4 (F-75; knowledge/findings/interpolated-level-finer-than-paise-refused.json): every level the engine
derives (breakevens, after-charges breakevens, loss-region edges, booked-P&L-shifted breakevens) is rounded to the 0.01
point step at the ONE place it is produced (``ofo.engine.metrics._to_decimal``), half-even (scenario-calculations.md
§3, the same rule ``engine.display.format_points`` prints with), so POP never refuses a level with a ValueError.

Expected values never come from the code under test: 22771.372 -> 22771.37 is the F-75 real case; the ADJ-23
after-charges breakevens are the generator's exact hand values (22547.488 / 23502.512) rounded here by hand.
"""
from __future__ import annotations

import datetime
import json
from decimal import Decimal as D
from pathlib import Path

import pytest
from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.metrics import breakevens_with_shift, loss_regions_after_charges, strategy_metrics
from ofo.engine.pop import Unavailable, probability_of_profit
from ofo.engine.strategy import Strategy
from ofo.money import HUNDREDTH

EXP = datetime.date(2026, 11, 3)
FIX = Path(__file__).resolve().parents[1] / "fixtures" / "adjust_scenarios"
FORWARD, YEARS, VOL = D("23020"), D("0.011"), D("0.13")


def _leg(action: Action, kind: Instrument, strike: str, entry: str, qty: int = 130) -> Leg:
    return Leg(action, kind, D(strike), EXP, qty, D(entry))


def _sold_put(entry: str, qty: int = 1) -> Strategy:
    return Strategy((_leg(Action.SELL, Instrument.PE, "22800", entry, qty),))


def _levels(regions) -> list[D]:
    return [x for r in regions for x in (r[0], r[1], *(r[2] if len(r) > 2 else ())) if x is not None]


def test_ac4_f75_level_22771_372_becomes_22771_37_at_the_producer():
    """A sold 22,800 PE at 28.628 points net of charges crosses zero at 22771.372 exactly (terminating, 3 decimals):
    entry 30.00 x 1000 units, charges 1372 -> 28.628 per unit. The producer gives 22771.37, never 22771.372."""
    put = _sold_put("30.00", 1000)
    assert breakevens_with_shift(put, D("-1372")) == (D("22771.37"),)
    assert loss_regions_after_charges(put, D("1372")) == ((None, D("22771.37")),)


def test_ac4_half_way_level_rounds_half_even_as_stated():
    """Attack 1: a level exactly on .xx5 rounds half-even (the §3 rule, same as the display): 22771.365 -> 22771.36,
    22771.375 -> 22771.38."""
    put = _sold_put("30.00", 1000)
    assert breakevens_with_shift(put, D("-1365")) == (D("22771.36"),)  # 22800 - 28.635 = 22771.365
    assert breakevens_with_shift(put, D("-1375")) == (D("22771.38"),)  # 22800 - 28.625 = 22771.375


def test_ac4_strategy_metrics_breakevens_are_paise():
    """No charges at all: SELL 1000 x 22,800 PE @ 30.01 + BUY 8 x 22,700 PE @ 0.05 is worth 30,010 - 0.40 = 30,009.60
    at 22,800 with slope -1000 below it, so its own crossing is 22800 - 30.0096 = 22769.9904 -> 22769.99."""
    s = Strategy((_leg(Action.SELL, Instrument.PE, "22800", "30.01", 1000),
                  _leg(Action.BUY, Instrument.PE, "22700", "0.05", 8)))
    assert strategy_metrics(s).breakevens == (D("22769.99"),)


def test_ac4_property_non_round_prices_and_charges_give_pop_or_unavailable_never_valueerror():
    """F-75 detection: real-chain-shaped iron condors (NIFTY 50-point strikes, lot 65, entries on the 0.05 tick) with
    non-round charges; every one gives a POP in [0, 1] (or the named Unavailable), never ValueError. Deterministic."""
    checked = 0
    finer_than_paise_before = 0
    for i in range(240):
        width = 100 + 50 * (i % 4)
        short_put = 22600 + 50 * (i % 5)
        short_call = 23400 + 50 * (i % 3)
        e = [D(35 + (i * 7) % 40) + D("0.05") * (i % 20), D(10 + (i * 3) % 15) + D("0.05") * ((i + 3) % 20),
             D(30 + (i * 11) % 30) + D("0.05") * ((i + 7) % 20), D(8 + (i * 5) % 12) + D("0.05") * ((i + 11) % 20)]
        qty = 65 * (1 + i % 3)
        s = Strategy((
            Leg(Action.SELL, Instrument.PE, D(short_put), EXP, qty, e[0]),
            Leg(Action.BUY, Instrument.PE, D(short_put - width), EXP, qty, e[1]),
            Leg(Action.SELL, Instrument.CE, D(short_call), EXP, qty, e[2]),
            Leg(Action.BUY, Instrument.CE, D(short_call + width), EXP, qty, e[3]),
        ))
        charges = D("150") + D("0.01") * ((i * 37) % 9973)
        # the exact crossing (credit - charges) / qty below the short put: count the members of the F-75 class
        credit = (e[0] - e[1] + e[2] - e[3]) * qty
        if ((credit - charges) / qty).as_tuple().exponent < -2:
            finer_than_paise_before += 1
        try:
            p = probability_of_profit(s, forward=FORWARD, years=YEARS, vol=VOL, charges=charges)
        except Unavailable:
            continue
        assert D(0) <= p <= D(1)
        for level in _levels(loss_regions_after_charges(s, charges)):
            assert level == level.quantize(HUNDREDTH), level
        checked += 1
    assert checked == 240
    assert finer_than_paise_before > 100  # the loop really exercises the class, not only round levels


def test_ac4_adj23_gives_a_pop_and_paise_after_charges_breakevens():
    """ADJ-23 (scenario library, F-75 regression): charges 199.94 put the after-charges breakevens at 22547.488 and
    23502.512 (the file's exact hand values); the producer gives 22547.49 / 23502.51 and POP is a number."""
    sc = json.loads((FIX / "ADJ-23.json").read_text(encoding="utf-8"))
    legs = tuple(Leg(Action(x["side"]), Instrument(x["type"]), D(x["strike"]), datetime.date.fromisoformat(x["expiry"]),
                     x["quantity"], D(x["entry"])) for x in sc["position"]["legs"])
    s = Strategy(legs)
    charges = D(sc["position"]["charges_round_trip"])
    assert sc["expected"]["at_expiry_after_charges"]["breakevens"] == ["22547.488", "23502.512"]
    assert breakevens_with_shift(s, -charges) == (D("22547.49"), D("23502.51"))
    assert loss_regions_after_charges(s, charges) == ((None, D("22547.49")), (D("23502.51"), None))
    p = probability_of_profit(s, forward=D(sc["market"]["spot"]), years=D(sc["dte"]) / D(365),
                              vol=D(sc["market"]["atm_iv"]), charges=charges)
    assert D("0.5") < p < D(1)


@pytest.mark.parametrize("shift", [D("0"), D("962"), D("-199.94")])
def test_ac4_round_levels_are_unchanged(shift):
    """Every shift gives levels on the step, and a level already on paise is returned exactly (ADJ-13's legs keep
    their hand breakevens with booked +962)."""
    s = Strategy((_leg(Action.SELL, Instrument.PE, "22900", "16.85"),
                  _leg(Action.BUY, Instrument.PE, "22700", "6.10"),
                  _leg(Action.SELL, Instrument.CE, "23450", "36.90"),
                  _leg(Action.BUY, Instrument.CE, "23650", "15.50")))
    for level in breakevens_with_shift(s, shift):
        assert level == level.quantize(HUNDREDTH)
    assert breakevens_with_shift(s, D("962")) == (D("22860.45"), D("23489.55"))  # ADJ-13 hand values


def test_ac4_a_level_that_rounds_to_zero_is_not_a_breakeven():
    """§3: breakevens only above 0. SELL 1000 x 1.00 PE @ 0.99 plus +7 booked is -3 at level 0 with slope 1000, so its
    zero is 0.003, which rounds to 0.00 and is dropped; without the shift the zero is 0.01 and is kept."""
    s = Strategy((_leg(Action.SELL, Instrument.PE, "1.00", "0.99", 1000),))
    assert breakevens_with_shift(s, D("7")) == ()
    assert breakevens_with_shift(s, D("0")) == (D("0.01"),)


def test_ac4_two_zeros_that_round_to_one_level_are_reported_once():
    """Judgement (§3 breakevens are levels; ADR-072 carries a sub-paisa stretch in the loss regions): SELL 1 x 22,000
    CE @ 0.01 + SELL 999 x 22,000 CE @ 0 + SELL 1000 x 22,000 PE @ 0 is +0.01 at 22,000 with slope 1000 each side, so
    its exact zeros are 21,999.99999 and 22,000.00001; both round to 22,000.00, reported ONCE, and the loss regions
    still name the peak as an except level (the profit point is never called a loss)."""
    s = Strategy((_leg(Action.SELL, Instrument.CE, "22000", "0.01", 1),
                  _leg(Action.SELL, Instrument.CE, "22000", "0", 999),
                  _leg(Action.SELL, Instrument.PE, "22000", "0", 1000)))
    m = strategy_metrics(s)
    assert m.breakevens == (D("22000.00"),)
    assert m.loss_regions == ((None, None, (D("22000"),)),)
