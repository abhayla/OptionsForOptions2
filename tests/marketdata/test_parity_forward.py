"""REQ-072 AC-3 / ADR-061: each expiry's put-call-parity forward, proven on the real 2026-10-08 recording (W-060 core).

Expected values are the orchestrator's independent computation from the same bytes (work/W-060.md ``proof``), never
taken from running this code.
"""
import dataclasses
import datetime
import math
from decimal import Decimal

import pytest

from ofo.engine.black_scholes import implied_volatility, year_fraction
from ofo.engine.inputs import LegInput, StrategyInput
from ofo.engine.legs import Action, Instrument
from ofo.marketdata.forward import (FALLBACK_LABEL, PARITY, SPOT_FALLBACK, ExpiryForward, ForwardUnavailable,
                                    mid_price, parity_forward)
from ofo.marketdata.kite_provider import IST, SOURCE
from ofo.marketdata.quote import NormalizedQuote
from ofo.rules.inputs import DataHealth
from ofo.scenario.config import ScenarioSettings
from ofo.scenario.forward_model import estimate_now_on_forward, greeks_on_forward, iv_on_forward
from ofo.scenario.levels import build_level_set
from ofo.scenario.views import View, scenario_values

from _kite_fixture import all_instrument_ids, new_provider, replay

VALUATION = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)
RATE = Decimal("0.065")
D = datetime.date
# (index, expiry): (spot, forward, strikes used, effective spot) - work/W-060.md proof
EXPECTED = {
    ("NIFTY", D(2026, 10, 13)): (Decimal("22533.25"), Decimal("22529.17"), 21, Decimal("22508.09")),
    ("NIFTY", D(2026, 10, 19)): (Decimal("22533.25"), Decimal("22551.77"), 20, Decimal("22506.61")),
    ("SENSEX", D(2026, 10, 8)): (Decimal("72443.48"), Decimal("72383.06"), 21, Decimal("72379.75")),
    ("SENSEX", D(2026, 10, 15)): (Decimal("72443.48"), Decimal("72452.96"), 21, Decimal("72359.39")),
}
TOL = Decimal("0.01")


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


def _forward(provider, name, expiry):
    spot = provider.underlying_quote(name)
    return parity_forward(provider.option_chain_snapshot(name, expiry), spot, expiry, VALUATION, RATE)


@pytest.mark.parametrize("key", list(EXPECTED))
def test_forward_per_expiry_matches_the_independent_values(replayed, key):
    spot, forward, used, effective = EXPECTED[key]
    f = _forward(replayed, *key)
    assert f.source == PARITY and f.label is None
    assert f.spot == spot
    assert abs(f.forward - forward) <= TOL, (f.forward, forward)
    assert abs(f.effective_spot - effective) <= TOL, (f.effective_spot, effective)
    assert f.strikes_used == used
    assert f.strikes_considered == 21
    q, t = float(f.implied_yield), float(f.years)  # stored figure: S e^(-qT) == F e^(-rT)
    assert abs(Decimal(repr(float(spot) * math.exp(-q * t))).quantize(TOL) - f.effective_spot) <= TOL


def test_quality_spread_is_the_filtered_figure_from_the_work_item(replayed):
    # work/W-060.md "Measured robustness": SENSEX 15-Oct filtered spread 9.98 points (192.61 unfiltered)
    assert _forward(replayed, "SENSEX", D(2026, 10, 15)).quality_spread == Decimal("9.98")


def _atm_iv_gap(provider, name, expiry, level):
    f = _forward(provider, name, expiry)
    chain = provider.option_chain_snapshot(name, expiry)
    by = {(q.strike, q.instrument_type): q for q in chain}
    strikes = sorted({k for k, _ in by})
    atm = min(strikes, key=lambda k: abs(k - f.spot))
    ivs = []
    for kind in (Instrument.CE, Instrument.PE):
        q = by[(atm, kind)]
        ivs.append(implied_volatility(kind, mid_price(q.bid, q.ask), level(f), atm, f.years, RATE))
    return abs(ivs[0] - ivs[1]) * 100  # vol points


@pytest.mark.parametrize("key", list(EXPECTED))
def test_iv_from_forward_closes_the_call_put_gap_where_spot_does_not(replayed, key):
    on_forward = _atm_iv_gap(replayed, *key, level=lambda f: f.effective_spot)
    on_spot = _atm_iv_gap(replayed, *key, level=lambda f: f.spot)
    assert on_forward < Decimal("0.5"), on_forward
    assert on_spot > Decimal("0.5"), on_spot


def test_iv_on_forward_closes_the_atm_gap_on_real_data(replayed):
    for name, expiry in EXPECTED:
        f = _forward(replayed, name, expiry)
        by = {(q.strike, q.instrument_type): q for q in replayed.option_chain_snapshot(name, expiry)}
        atm = min({k for k, _ in by}, key=lambda k: abs(k - f.spot))
        ivs = [iv_on_forward(kind, mid_price(by[(atm, kind)].bid, by[(atm, kind)].ask), atm, f).iv
               for kind in (Instrument.CE, Instrument.PE)]
        assert abs(ivs[0] - ivs[1]) * 100 < Decimal("0.5"), (name, expiry, ivs)


# ---- the forward's answer states (run-discipline B4 (d)), on synthetic chains built from a known forward --------
E = D(2026, 10, 13)
S = Decimal("22000.00")
F_TRUE = 22050.0
T = float(year_fraction(VALUATION, E))


def _q(kind, strike, bid, ask, health=DataHealth.AVAILABLE):
    return NormalizedQuote(
        instrument_id=f"NSE_FO:{strike}{kind.value}", underlying="NIFTY", exchange="NSE", segment="NSE_FO",
        instrument_type=kind, expiry=E, strike=Decimal(strike), ltp=None, bid=Decimal(bid), ask=Decimal(ask),
        volume=None, oi=None, oi_change=None, iv=None, delta=None, gamma=None, theta=None, vega=None,
        timestamp=VALUATION, source=SOURCE, health=health)


def _spot(level=S, health=DataHealth.AVAILABLE):
    return NormalizedQuote(
        instrument_id="NSE_INDEX:1001", underlying="NIFTY", exchange="NSE", segment="NSE_INDEX", instrument_type=None,
        expiry=None, strike=None, ltp=level, bid=None, ask=None, volume=None, oi=None, oi_change=None, iv=None,
        delta=None, gamma=None, theta=None, vega=None, timestamp=VALUATION, source=SOURCE, health=health)


def _chain(strikes=(21900, 21950, 22000, 22050, 22100)):
    """Put mid 100.00 at every strike; call mid from parity C = P + e^(-rT)(F - K), to 0.01; quotes 1.00 wide."""
    out = []
    for k in strikes:
        c_mid = (Decimal("100.00") + Decimal(repr(math.exp(-0.065 * T) * (F_TRUE - k)))).quantize(TOL)
        out.append(_q(Instrument.CE, str(k), c_mid - Decimal("0.50"), c_mid + Decimal("0.50")))
        out.append(_q(Instrument.PE, str(k), "99.50", "100.50"))
    return out


def test_state_enough_strikes_recovers_the_known_forward():
    f = parity_forward(_chain(), _spot(), E, VALUATION, RATE)
    assert f.source == PARITY and f.strikes_used == 5 and f.label is None
    assert abs(f.forward - Decimal("22050.00")) <= TOL
    q = 0.065 - math.log(F_TRUE / 22000.0) / T  # q = r - ln(F/S)/T
    assert abs(float(f.implied_yield) - q) < 1e-3
    assert abs(f.effective_spot - Decimal(repr(22000.0 * math.exp(-q * T))).quantize(TOL)) <= TOL


def test_state_fewer_than_three_strikes_falls_back_with_the_label():
    f = parity_forward(_chain((22000, 22050)), _spot(), E, VALUATION, RATE)
    assert f.source == SPOT_FALLBACK and f.strikes_used == 2
    assert f.label == FALLBACK_LABEL == "estimated from spot"
    assert f.effective_spot == S and f.implied_yield == 0
    assert iv_on_forward(Instrument.PE, Decimal("100.00"), Decimal("22000"), f).label == "estimated from spot"


@pytest.mark.parametrize("spot", [None, "stale", "unavailable"])
def test_state_spot_missing_or_not_available_refuses(spot):
    quote = None if spot is None else _spot(health=DataHealth(spot))
    with pytest.raises(ForwardUnavailable):
        parity_forward(_chain(), quote, E, VALUATION, RATE)


def test_state_expired_refuses():
    after_close = datetime.datetime(2026, 10, 13, 15, 30, tzinfo=IST)
    with pytest.raises(ForwardUnavailable, match="expired"):
        parity_forward(_chain(), _spot(), E, after_close, RATE)


def test_state_crossed_strike_is_skipped_and_counted():
    chain = _chain()
    chain[0] = _q(Instrument.CE, "21900", "160.00", "150.00")  # ask below bid
    f = parity_forward(chain, _spot(), E, VALUATION, RATE)
    assert f.crossed_skipped == 1 and f.strikes_used == 4 and f.source == PARITY


def test_stale_option_quotes_are_not_used():
    chain = [dataclasses.replace(q, health=DataHealth.STALE) if q.strike != Decimal("22000") else q for q in _chain()]
    assert parity_forward(chain, _spot(), E, VALUATION, RATE).source == SPOT_FALLBACK


# ---- IV / Greeks / Estimated Now on the forward, against Hull's formulas for an index paying yield q -------------
def _ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _hull(s, k, t, r, q, v, put=False):
    """Hull ch. 17-19, European option on an asset paying a continuous yield q; theta per calendar day (365)."""
    d1 = (math.log(s / k) + (r - q + v * v / 2) * t) / (v * math.sqrt(t))
    d2 = d1 - v * math.sqrt(t)
    pdf = math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi)
    sq, kr = s * math.exp(-q * t), k * math.exp(-r * t)
    decay = -sq * pdf * v / (2 * math.sqrt(t))
    if put:
        return {"price": kr * _ncdf(-d2) - sq * _ncdf(-d1), "delta": math.exp(-q * t) * (_ncdf(d1) - 1),
                "theta": (decay + r * kr * _ncdf(-d2) - q * sq * _ncdf(-d1)) / 365,
                "gamma": math.exp(-q * t) * pdf / (s * v * math.sqrt(t)), "vega": sq * pdf * math.sqrt(t) / 100}
    return {"price": sq * _ncdf(d1) - kr * _ncdf(d2), "delta": math.exp(-q * t) * _ncdf(d1),
            "theta": (decay - r * kr * _ncdf(d2) + q * sq * _ncdf(d1)) / 365,
            "gamma": math.exp(-q * t) * pdf / (s * v * math.sqrt(t)), "vega": sq * pdf * math.sqrt(t) / 100}


def _hull_call(s, k, t, r, q, v):
    return _hull(s, k, t, r, q, v)


def _synthetic_forward(q="0.5", years="1"):
    return ExpiryForward(expiry=E, forward=Decimal("0"), implied_yield=Decimal(q), effective_spot=Decimal("0"),
                         strikes_used=21, quality_spread=None, source=PARITY, spot=Decimal("100.00"),
                         spot_timestamp=VALUATION, years=Decimal(years), rate=RATE, valuation_time=VALUATION)


@pytest.mark.parametrize("kind", [Instrument.CE, Instrument.PE])
def test_every_greek_follows_hull_for_a_dividend_yield(kind):
    f = _synthetic_forward()  # qT = 0.5: e^(-qT) = 0.61, so a missing yield factor is far outside 4 dp
    g = greeks_on_forward(kind, Decimal("100"), Decimal("0.2"), f).greeks
    h = _hull(100.0, 100.0, 1.0, 0.065, 0.5, 0.2, put=kind is Instrument.PE)
    for name in ("delta", "gamma", "theta", "vega"):
        assert abs(float(getattr(g, name)) - h[name]) <= 1e-4, (name, getattr(g, name), h[name])


# The review's (ADR-063) theta values were computed with the yield read from UNROUNDED mids (q below); the forward
# here uses paise-rounded mids (work/W-060.md proof), which moves SENSEX 08-Oct q to 1.25071 and theta to -111.05.
# So the review's numbers are pinned at the review's inputs, and the live forward is checked against Hull separately.
@pytest.mark.parametrize("key, strike, vol, q, theta", [
    (("SENSEX", D(2026, 10, 8)), "72400", "0.15", "1.2505103235", Decimal("-111.07")),  # code was -229.44
    (("NIFTY", D(2026, 10, 13)), "22550", "0.12", "0.0775980093", Decimal("-11.89")),  # code was -14.17
])
def test_theta_carries_the_yield_term(replayed, key, strike, vol, q, theta):
    live = _forward(replayed, *key)
    review = dataclasses.replace(live, implied_yield=Decimal(q))
    g = greeks_on_forward(Instrument.CE, Decimal(strike), Decimal(vol), review).greeks
    assert abs(g.theta - theta) <= Decimal("0.005"), g.theta
    g_live = greeks_on_forward(Instrument.CE, Decimal(strike), Decimal(vol), live).greeks
    h = _hull(float(live.spot), float(strike), float(live.years), 0.065, float(live.implied_yield), float(vol))
    assert abs(float(g_live.theta) - h["theta"]) <= 1e-4


def test_estimate_refuses_a_forward_read_for_another_valuation_rate_or_day_count(replayed):
    f = _forward(replayed, "NIFTY", D(2026, 10, 13))
    inputs = _one_call(f.spot)
    for bad in (dataclasses.replace(f, valuation_time=VALUATION + datetime.timedelta(minutes=1)),
                dataclasses.replace(f, rate=Decimal("0.07")), dataclasses.replace(f, days_in_year=252)):
        with pytest.raises(ForwardUnavailable, match="different"):
            estimate_now_on_forward(inputs, f.spot, {f.expiry: bad})


def test_a_non_positive_median_forward_refuses_not_a_math_error():
    # deep calls priced far below their puts: K + e^(rT)(C - P) < 0 at every strike
    chain = []
    for k in (100, 110, 120):
        chain += [_q(Instrument.CE, str(k), "1.00", "1.10"), _q(Instrument.PE, str(k), "5000.00", "5000.10")]
    with pytest.raises(ForwardUnavailable, match="median"):
        parity_forward(chain, _spot(Decimal("110.00")), E, VALUATION, RATE)


def test_delta_on_the_real_nifty_forward_follows_hull(replayed):
    f = _forward(replayed, "NIFTY", D(2026, 10, 13))
    g = greeks_on_forward(Instrument.CE, Decimal("22550"), Decimal("0.12"), f).greeks
    h = _hull_call(float(f.spot), 22550.0, float(f.years), 0.065, float(f.implied_yield), 0.12)
    assert abs(float(g.delta) - h["delta"]) <= 1e-4


def _one_call(spot):
    leg = LegInput(underlying="NIFTY", contract="NSE_FO:44614", action=Action.BUY, instrument=Instrument.CE,
                   strike=Decimal("22550"), expiry=D(2026, 10, 13), quantity=65, premium=Decimal("100.00"),
                   iv=Decimal("0.12"))
    return StrategyInput(underlying="NIFTY", underlying_level=spot, valuation_time=VALUATION, rate=RATE, legs=(leg,))


def test_estimated_now_marks_at_the_effective_level_per_hull(replayed):
    f = _forward(replayed, "NIFTY", D(2026, 10, 13))
    est = estimate_now_on_forward(_one_call(f.spot), f.spot, {f.expiry: f})
    h = _hull_call(float(f.spot), 22550.0, float(f.years), 0.065, float(f.implied_yield), 0.12)
    expected = (Decimal(repr(h["price"])).quantize(TOL) - Decimal("100.00")) * 65
    assert abs(est.total - expected) <= Decimal("0.65")  # one paisa of price rounding x 65 (one lot)
    assert est.dividend_yields == (f.implied_yield,) and est.level == f.spot and est.label is None
    no_yield = _hull_call(float(f.spot), 22550.0, float(f.years), 0.065, 0.0, 0.12)["price"]
    on_spot = (Decimal(repr(no_yield)).quantize(TOL) - Decimal("100.00")) * 65
    assert abs(est.total - on_spot) > Decimal("100")  # spot would be visibly off (about 25 points x delta x 65)


def test_estimate_refuses_a_leg_with_no_forward(replayed):
    f = _forward(replayed, "NIFTY", D(2026, 10, 19))
    with pytest.raises(ForwardUnavailable):
        estimate_now_on_forward(_one_call(f.spot), f.spot, {f.expiry: f})


def test_scenario_estimated_now_uses_the_forward_and_payoff_keeps_spot(replayed):
    f = _forward(replayed, "NIFTY", D(2026, 10, 13))
    inputs = _one_call(f.spot)
    ls = build_level_set(inputs, ScenarioSettings().for_index("NIFTY"))
    assert ls.current == f.spot  # CURRENT column and the range stay on spot
    on_fwd = scenario_values(ls, inputs, View.ESTIMATED_NOW, forwards={f.expiry: f})
    on_spot = scenario_values(ls, inputs, View.ESTIMATED_NOW)
    assert on_fwd.model_label is None and on_spot.model_label == "estimated from spot"
    assert on_fwd.totals != on_spot.totals
    at_exp = scenario_values(ls, inputs, View.AT_EXPIRY, forwards={f.expiry: f})
    assert at_exp.totals == scenario_values(ls, inputs, View.AT_EXPIRY).totals
    fallback = dataclasses.replace(f, source=SPOT_FALLBACK, implied_yield=Decimal(0), effective_spot=f.spot)
    assert scenario_values(ls, inputs, View.ESTIMATED_NOW, forwards={f.expiry: fallback}).model_label == FALLBACK_LABEL
