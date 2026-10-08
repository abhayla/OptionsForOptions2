"""REQ-072 AC-3 / ADR-061: each expiry's put-call-parity forward, proven on the real 2026-10-08 recording (W-060 core).

Expected values are the orchestrator's independent computation from the same bytes (work/W-060.md ``proof``), never
taken from running this code.
"""
import datetime
from decimal import Decimal

import pytest

from ofo.engine.black_scholes import implied_volatility
from ofo.engine.legs import Instrument
from ofo.marketdata.forward import PARITY, mid_price, parity_forward
from ofo.marketdata.kite_provider import IST

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
    assert f.level_for(spot) == f.effective_spot  # S e^(-qT) == F e^(-rT)


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
