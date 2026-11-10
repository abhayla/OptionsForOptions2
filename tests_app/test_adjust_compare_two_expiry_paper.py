"""C12 round 2 (paper path): the paper condor's market read (``adjustment_readers.read_market``, the reader the
approaches route uses for the paper book) gives A-04's later-expiry legs their engine IV and the rate, so the Compare's
four spot moves are numbers "(estimated at the nearer expiry)", never "no implied volatility"."""
from __future__ import annotations

import dataclasses
from decimal import Decimal

from ofo.adjustment.compare import Column, Context, MarginRead, compare
from ofo.marketdata.spot_source import resolve_spot
from ofo_app import adjustment_check, adjustment_readers
from ofo_app.routes.adjustment import priced_approach
from ofo_app.routes.outcome import MarketContext, ctx_in_force
from test_adjustment_approaches_route import RATES
from test_background_cycle import DEFAULTS, PREFS, RATE, Prov, _price_time, _tracked, scenario_on, scn  # noqa: F401


async def test_core_paper_condor_a04_spot_moves_are_estimated_numbers(scn, scenario_on):  # noqa: F811
    prov = Prov(scn)
    at = _price_time(prov)
    tracked = dataclasses.replace(_tracked(scn), paid_charges=Decimal(0))  # the paper book's paid charges, read
    ctx = ctx_in_force(MarketContext(prov, lambda: at, RATE), DEFAULTS)
    market = await adjustment_readers.read_market(tracked, ctx)
    spot = resolve_spot(market.feed, None, market.last_close, now=market.now, windows=ctx.feed_windows)
    basis = adjustment_check.basis_in_force(None, None, None)
    built, priced = priced_approach("A-04", tracked, market, spot.value, RATES, PREFS.approach, roll_basis=basis)
    assert built is not None and built.refusal is None, built and built.refusal_message
    later = {x.tradingsymbol for x in built.after if x.expiry > min(y.expiry for y in built.after)}
    assert later and later <= set(market.leg_ivs), (later, sorted(market.leg_ivs))  # the engine's IV of each new leg
    assert priced.near is not None, priced.reason
    col = Column(built, priced.after, priced.reason, priced.charges_known, MarginRead(None), priced.adjustment_charges,
                 priced.near)
    c = Context(tracked.position, spot.value, market.chain, RATES, False, MarginRead(None), market.leg_greeks, 0,
                PREFS.compare)
    rows = {r.id: r.values["A-04"] for r in compare([col], c).criteria}
    for row in ("move_m2", "move_m1", "move_p1", "move_p2"):
        assert rows[row].value is not None and rows[row].text.endswith("(estimated at the nearer expiry)"), rows[row]
    assert rows["delta"].value is not None  # Greeks after: the later legs' Greeks come from the same read


async def test_paper_charges_unknown_says_so_not_one_expiry(scn, scenario_on):  # noqa: F811
    prov = Prov(scn)
    at = _price_time(prov)
    tracked = _tracked(scn)  # paid charges None: not read
    ctx = ctx_in_force(MarketContext(prov, lambda: at, RATE), DEFAULTS)
    market = await adjustment_readers.read_market(tracked, ctx)
    spot = resolve_spot(market.feed, None, market.last_close, now=market.now, windows=ctx.feed_windows)
    built, priced = priced_approach("A-04", tracked, market, spot.value, RATES, PREFS.approach,
                                    roll_basis=adjustment_check.basis_in_force(None, None, None))
    col = Column(built, priced.after, priced.reason, priced.charges_known, MarginRead(None), priced.adjustment_charges,
                 priced.near)
    c = Context(tracked.position, spot.value, market.chain, RATES, False, MarginRead(None), market.leg_greeks, 0,
                PREFS.compare)
    cell = next(r for r in compare([col], c).criteria if r.id == "move_m1").values["A-04"]
    assert cell.value is None
    assert cell.unavailable_reason == "Charges not available, so the figures after charges are not shown."
