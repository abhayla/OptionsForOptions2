"""D-08 / D-12 (23 Nov live test; ADR-320 (1), ADR-268 (1), ADR-008): the engine on expiry day.

D-08: on expiry day the Estimated-now figures and the what-if use the real time left to the 15:30 IST close; at zero
time left the value is intrinsic. C2 157 read "Estimate not available" at 14:50 .. 15:25: a leg whose price sat at its
intrinsic value had no solvable IV and the whole now-curve was dropped. Rule taken (ADR-268 (1), the nearest decision):
an option whose IV is not solvable while its price is within one tick (0.05) of its intrinsic value at the live spot
has no time value left, so it is valued at its intrinsic value at every level (its At Expiry value), never dropped.

D-12: theta per day (annual / 365) is replaced on expiry day by "Decay left today: Rs X" = the model value at today's
close minus the value now, per unit x quantity x sign (the Decay column's sign: a seller gains it).

The C2-shaped book (NIFTY, 1 lot of 65, expiry 25 Nov 2026): BUY 25200 PE @ 16.00, SELL 25300 PE @ 22.05,
SELL 25900 CE @ 4.10, BUY 26000 CE @ 2.70; at 12:30 IST, spot 25,600, live 3.10 / 4.20 / 1.05 / 0.60 (all out of the
money, so every live price is all time value). Hand sums:
  At the close, 25,300: every leg expires worthless -> P&L = credit = (22.05 - 16.00 + 4.10 - 2.70) x 65
  = 7.45 x 65 = +484.25. At 25,900 the same +484.25 (25900 CE worth 0 at 25,900).
  Decay left today (position) = the time value still in the book: sells 4.20 + 1.05 - buys 3.10 + 0.60 = 1.55 per
  unit x 65 = +100.75 (the IV is solved from these prices, so model value now = the price, to a paisa).
  Theta per day at the same instant is thousands of rupees (the 23 Nov screen: +4,008/day vs ~448 of value).
"""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal as D

from ofo.engine.black_scholes import IST, NoImpliedVolatilityError, implied_volatility, year_fraction
from ofo.engine.inputs import LegInput, SpotReading, StrategyInput
from ofo.engine.legs import Action, Instrument
from ofo.engine.model import estimate, expiry_day_close, leg_decay_left_today, legs_without_estimate
from ofo.rules.inputs import DataHealth
from ofo.table import build_table
from ofo.table.columns import ColumnId
from scenario.scenario_fixtures import gated

EXPIRY = datetime.date(2026, 11, 25)
RATE = D("0.065")
LOT = 65
NOON = datetime.datetime(2026, 11, 25, 12, 30, tzinfo=IST)
CLOSE = datetime.datetime(2026, 11, 25, 15, 30, tzinfo=IST)
C2 = ((Action.BUY, Instrument.PE, "25200", "16.00", "3.10"), (Action.SELL, Instrument.PE, "25300", "22.05", "4.20"),
      (Action.SELL, Instrument.CE, "25900", "4.10", "1.05"), (Action.BUY, Instrument.CE, "26000", "2.70", "0.60"))


def _iv(kind, price, spot, strike, when):
    try:
        return implied_volatility(kind, D(price), D(spot), D(strike), year_fraction(when, EXPIRY), RATE)
    except NoImpliedVolatilityError:  # the outcome's own answer: no IV for this price
        return None


def _model(legs=C2, spot="25600", when=NOON):
    built = tuple(LegInput("NIFTY", f"NIFTY{k}{kind.value}", act, kind, D(k), EXPIRY, LOT, D(entry), D(ltp),
                           _iv(kind, ltp, spot, k, when)) for act, kind, k, entry, ltp in legs)
    return gated(StrategyInput(underlying="NIFTY", valuation_time=when, rate=RATE, legs=built,
                               spot=SpotReading(level=D(spot), at=when, health=DataHealth.AVAILABLE)))


def test_estimate_at_zero_time_left_is_the_hand_expiry_figure():
    m = _model()
    assert estimate(m, D("25300"), CLOSE).total == D("484.25")
    assert estimate(m, D("25900"), CLOSE).total == D("484.25")


def test_a_leg_at_intrinsic_with_no_iv_is_valued_at_intrinsic_not_dropped():
    # 15:25 (5 min left), spot 25,280: the short 25300 PE is 20 in the money, quoted 19.96: within one tick of its
    # intrinsic 20.00 and under its discounted intrinsic (about 19.98) -> no IV (round 2: 19.85 is more than a tick
    # under intrinsic and now keeps the refusal)
    legs = ((Action.BUY, Instrument.PE, "25200", "16.00", "0.40"),
            (Action.SELL, Instrument.PE, "25300", "22.05", "19.96"),
            (Action.SELL, Instrument.CE, "25900", "4.10", "0.05"), (Action.BUY, Instrument.CE, "26000", "2.70", "0.05"))
    when = datetime.datetime(2026, 11, 25, 15, 25, tzinfo=IST)
    m = _model(legs, "25280", when)
    assert m.legs[1].iv is None
    assert legs_without_estimate(m) == []  # the now-curve is not "Estimate not available"
    got = estimate(m, D("25250"))
    assert got.marks[1] == D("50.00")  # the 25300 PE at its intrinsic value at 25,250


def test_a_leg_with_no_iv_and_time_value_left_still_refuses():
    when = datetime.datetime(2026, 11, 25, 14, 50, tzinfo=IST)
    m = _model(when=when)
    leg = m.legs[1]
    bare = gated(StrategyInput(underlying="NIFTY", valuation_time=when, rate=RATE,
                               legs=(LegInput(leg.underlying, leg.contract, leg.action, leg.instrument, leg.strike,
                                              leg.expiry, leg.quantity, leg.premium, leg.ltp, None),),
                               spot=SpotReading(level=D("25600"), at=when, health=DataHealth.AVAILABLE)))
    assert legs_without_estimate(bare) == [leg.contract]  # 4.20 out of the money is all time value: no guess


def test_decay_left_today_is_the_time_value_left_never_theta_per_day():
    m = _model()
    assert expiry_day_close(m) == CLOSE
    position = sum((leg_decay_left_today(m, leg) * (1 if leg.action is Action.BUY else -1) * leg.quantity
                    for leg in m.legs), D(0))
    assert position.quantize(D("0.01")) == D("100.75")
    table = build_table(m)
    total = next(r for r in table.rows if r.row_id == "TOTAL").cells[ColumnId.THETA]
    assert total.display == "100.75" and total.value.quantize(D("0.01")) == D("100.75")
    assert abs(total.value) <= D("100.75")  # never the 4,008-per-day class of figure
    heading = next(c for c in table.columns if c.id == ColumnId.THETA).label
    assert "Decay left today" in str(heading)


def test_other_days_unchanged():
    day_before = datetime.datetime(2026, 11, 24, 12, 30, tzinfo=IST)
    m = _model(when=day_before)
    assert expiry_day_close(m) is None
    heading = next(c for c in build_table(m).columns if c.id == ColumnId.THETA).label
    assert str(heading) == "Theta"


# --- D-08 round 2: the tick rule only on the leg's own expiry day, only within one tick, and labelled ---
from ofo.scenario.config import ScenarioSettings  # noqa: E402
from ofo.scenario.levels import build_level_set  # noqa: E402
from ofo.scenario.views import View, scenario_values  # noqa: E402
from ofo.settings import defaults as _defaults  # noqa: E402

BASIS = "a leg with no time value left at the live price is valued at its intrinsic value"
ITM_SHORT = (Action.SELL, Instrument.PE, "25300", "22.05")


def _with_short(ltp, spot, when):
    return _model((C2[0], (*ITM_SHORT, ltp), C2[2], C2[3]), spot, when)


def _curve(m):
    return scenario_values(build_level_set(m, ScenarioSettings.from_values(_defaults()).for_index("NIFTY")), m,
                           View.ESTIMATED_NOW)


def test_another_day_a_no_iv_leg_at_intrinsic_is_still_not_available():
    week = datetime.datetime(2026, 11, 18, 12, 30, tzinfo=IST)  # 7 days before the 25 Nov expiry
    m = _with_short("49.98", "25250", week)  # 25300 PE within a tick of intrinsic 50.00 a week out, its IV absent
    legs = tuple(dataclasses.replace(x, iv=None) if i == 1 else x for i, x in enumerate(m.legs))
    m = gated(dataclasses.replace(m.inputs, legs=legs))
    assert m.legs[1].iv is None
    assert legs_without_estimate(m) == [m.legs[1].contract]
    assert _curve(m).available is False


def test_expiry_day_an_ltp_more_than_a_tick_under_intrinsic_keeps_the_refusal():
    m = _with_short("30.00", "25250", NOON)  # intrinsic 50.00: a 30.00 price is not "at intrinsic" (ADR-019)
    assert m.legs[1].iv is None
    assert legs_without_estimate(m) == [m.legs[1].contract]
    assert _curve(m).available is False


def test_expiry_day_a_within_tick_leg_is_estimated_with_the_basis_line():
    late = datetime.datetime(2026, 11, 25, 15, 25, tzinfo=IST)  # 5 min left: discounted intrinsic about 49.98
    m = _with_short("49.96", "25250", late)  # within one tick of intrinsic 50.00 and under its discounted value: no IV
    assert m.legs[1].iv is None and legs_without_estimate(m) == []
    curve = _curve(m)
    assert curve.available is True
    assert BASIS in (curve.output_label or "")
    plain = _curve(_model())  # no leg valued at intrinsic: no basis line
    assert BASIS not in (plain.output_label or "")
