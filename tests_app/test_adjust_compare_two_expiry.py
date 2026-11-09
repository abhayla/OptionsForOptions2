"""C12 / GC-ICGUIDE g14 (REQ-148, ADR-143): the Compare of the ADJ-02 NIFTY weekly condor (lot 65, 2 lots) and A-04
(roll the call side to the next expiry) answers with an After instead of the MultiExpiryError dash.

A-04's After keeps the put side on 9 Nov and moves the call side to 17 Nov, so it is valued at the 9 Nov close: the
9 Nov legs at their expiry value, the 17 Nov legs at an independent Black-Scholes (math here, never the engine) with
their chain IV and 8 days left. Single at-expiry figures stay "-" with ADR-143's reason."""
from __future__ import annotations

import dataclasses
import datetime
import math
from decimal import ROUND_HALF_EVEN
from decimal import Decimal as D
from fractions import Fraction

from ofo.charges.calculator import ChargeOrder, charges_for_orders
from ofo.charges.round_trip import to_paise_up
from ofo.marketdata.forward import ExpiryForward
from ofo_app.routes import adjustment as route
from test_adjustment_approaches_route import RATES, client_for, gen, load, market_of, post

NEAR, FAR = "2026-11-09", "2026-11-17"
RATE = D("0.065")


def _forward(sc: dict) -> ExpiryForward:
    now = datetime.datetime.fromisoformat(sc["clock"]["ist"])
    spot = D(sc["market"]["spot"])
    return ExpiryForward(datetime.date(2026, 11, 9), spot, D(0), spot, 3, None, "parity", spot, now, D("0.01"), RATE,
                         now)


def _far_ivs(sc: dict) -> dict[str, D]:
    far = next(c for c in sc["market"]["chains"] if c["expiry"] == FAR)
    return {r["tradingsymbol"]: D(str(r["iv"])) for r in far["rows"] if r.get("iv") is not None}


def _client(sc: dict, *, ivs: bool = True, rate: bool = True):
    c = client_for(sc, rates=RATES)

    async def market(_t, _ctx):
        return dataclasses.replace(market_of(sc), forward_model=_forward(sc) if rate else None,
                                   leg_ivs=_far_ivs(sc) if ivs else {})
    c.app.dependency_overrides[route.get_market_reader] = lambda: market
    return c


def _charges(sc: dict) -> D:
    """paid (0 here) + this adjustment's orders + the After legs' exit orders, as the outcome prices them."""
    legs = sc["expected"]["approach_legs"]["A-04"]
    trades = [ChargeOrder("NSE_FO", t["action"], t["quantity"], D(t["price"])) for t in legs["trades"]]
    exits = [ChargeOrder("NSE_FO", "SELL" if x["side"] == "BUY" else "BUY", x["quantity"], D(x["entry"]))
             for x in legs["after"]]
    return sum((to_paise_up(charges_for_orders(o, RATES).total) for o in (trades, exits)), D(0))


def _bs(kind: str, s: float, k: float, t: float, r: float, v: float) -> float:  # noqa: PLR0913 - the BS inputs
    n = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))  # noqa: E731
    d1 = (math.log(s / k) + (r + v * v / 2) * t) / (v * math.sqrt(t))
    d2 = d1 - v * math.sqrt(t)
    call = s * n(d1) - k * math.exp(-r * t) * n(d2)
    return call if kind == "CE" else call - s + k * math.exp(-r * t)


def _hand_move(sc: dict, after: list[dict], booked: str, level: D, charges: D) -> D:
    ivs = _far_ivs(sc)
    near = [x for x in after if x["expiry"] == NEAR]
    total = D(str(float(gen.hand_pnl_at(near, Fraction(booked), Fraction(level)))))  # exact: whole paise here
    for x in after:
        if x["expiry"] == FAR:
            mark = D(str(round(_bs(x["type"], float(level), float(x["strike"]), 8 / 365, 0.065,
                                   float(ivs[x["tradingsymbol"]])), 2)))
            sign = 1 if x["side"] == "BUY" else -1
            total += sign * x["quantity"] * (mark - D(x["entry"]))
    return (total - charges).quantize(D("0.01"), rounding=ROUND_HALF_EVEN)


def _reply(**kw):
    sc = load("ADJ-02")
    return sc, post(_client(sc, **kw)).json()


def test_core_a04_compare_has_after_moves_and_curve_valued_at_the_nearer_expiry():
    sc, body = _reply()
    rows = {c["id"]: c["values"] for c in body["criteria"]}
    a04 = next(x for x in body["approaches"] if x["id"] == "A-04")
    after = sc["expected"]["approach_legs"]["A-04"]["after"]
    assert {x["expiry"] for x in after} == {NEAR, FAR}
    assert a04["after"] is None  # the approach block keeps its no-whole-trade answer
    charges = _charges(sc)
    for p, row in (("-2", "move_m2"), ("-1", "move_m1"), ("1", "move_p1"), ("2", "move_p2")):
        cell = rows[row]["A-04"]
        assert cell["value"] is not None, (row, cell)
        assert cell["text"].endswith("(estimated at the nearer expiry)"), cell["text"]
        level = (D(sc["market"]["spot"]) * (100 + D(p)) / 100).quantize(D("0.01"), rounding=ROUND_HALF_EVEN)
        want = _hand_move(sc, after, sc["expected"]["approach_after"]["A-04"]["booked_pnl"], level, charges)
        assert abs(D(cell["value"]) - want) <= D("0.01"), (row, cell["value"], want)
    assert "A-04" in body["curves"] and "before" in body["curves"]
    assert body["curves_estimated"] == {"A-04": "estimated at the nearer expiry"}  # the condor itself: an exact curve


def test_single_figures_say_not_available_with_adr143_reason():
    _, body = _reply()
    rows = {c["id"]: c["values"] for c in body["criteria"]}
    for row, words in (("max_loss", "Maximum loss: the loss for this strategy cannot be estimated."),
                       ("max_profit", "The most this strategy can make cannot be estimated"),
                       ("max_profit_change", "The most this strategy can make cannot be estimated"),
                       ("breakevens", "Where losses start cannot be estimated"),
                       ("pop", "POP not available: the probability figure is held")):
        cell = rows[row]["A-04"]
        assert cell["value"] is None and words in cell["unavailable_reason"], (row, cell)
    for row in ("credit", "cost"):  # answered as before
        assert rows[row]["A-04"]["value"] is not None, row


def test_far_leg_without_iv_names_the_leg():
    _, body = _reply(ivs=False)
    cell = {c["id"]: c["values"] for c in body["criteria"]}["move_m2"]["A-04"]
    assert cell["value"] is None
    assert "has no implied volatility to value it at the nearer expiry." in cell["unavailable_reason"]
    assert "A-04" not in body["curves"]


def test_no_rate_says_so():
    _, body = _reply(rate=False)
    cell = {c["id"]: c["values"] for c in body["criteria"]}["move_p1"]["A-04"]
    assert cell["value"] is None
    assert cell["unavailable_reason"] == "Not available: no interest rate was read to value the later expiry's legs."
