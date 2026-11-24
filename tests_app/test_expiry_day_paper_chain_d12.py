"""D-12 (ADR-320 (1)) server parts: the paper reply's Greeks and the option chain's cells on expiry day carry the
engine's "Decay left today" (``leg_decay_left_today`` / ``unit_decay_left_today``); on another day they do not.

Paper: the C2-shaped book of tests_app/test_charges_basis_d13_d14.py (NIFTY, 65 units, expiry 25 Nov 2026) at 12:30
IST, spot 25,600, live 3.10 / 4.20 / 1.05 / 0.60 (all out of the money: all time value). The snapshot is the route's
own input shape (``_greeks(figures, found, snapshot, underlying)``), built here without a database: the DB paper fixture
is a replay on a fixed non-expiry date. Hand sum: net decay left = (4.20 + 1.05 - 3.10 - 0.60) x 65 = +100.75; per leg
BUY 25200 PE -3.10 x 65 = -201.50, SELL 25300 PE +273.00, SELL 25900 CE +68.25, BUY 26000 CE -39.00.
Chain: the live chain rig of test_chain_live.py with its wall clock on the chain's own expiry day (12:30 IST)."""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from types import SimpleNamespace

from ofo.engine.legs import Instrument
from ofo.marketdata.forward import spot_fallback_forward
from ofo.marketdata.quote import NormalizedQuote, SourceMetadata
from ofo.rules.inputs import DataHealth
from ofo.timeutil import IST
from ofo_app.routes import paper as route

EXPIRY = datetime.date(2026, 11, 25)
NOON = datetime.datetime(2026, 11, 25, 12, 30, tzinfo=IST)
LEGS = ((1, Instrument.PE, "25200", 65, "3.10"), (2, Instrument.PE, "25300", -65, "4.20"),
        (3, Instrument.CE, "25900", -65, "1.05"), (4, Instrument.CE, "26000", 65, "0.60"))


def _quote(iid, kind, expiry, strike, ltp, at):
    return NormalizedQuote(iid, "NIFTY", "NSE", "NSE_FO" if kind else "INDICES", kind, expiry, strike, D(ltp), None,
                           None, None, None, None, None, None, None, None, None, at, SourceMetadata("fake", "fake-feed"),
                           DataHealth.AVAILABLE)


def _paper(at: datetime.datetime):
    spot = _quote("NIFTY-INDEX", None, None, None, "25600", at)
    fwd = spot_fallback_forward(EXPIRY, D("25600"), at, at, D("0.065"))
    snapshot = SimpleNamespace(spot=spot, valuation=at, rate=D("0.065"), forwards={EXPIRY: fwd},
                               legs={f"k{cid}": SimpleNamespace(quote=_quote(f"k{cid}", kind, EXPIRY, D(k), ltp, at))
                                     for cid, kind, k, _q, ltp in LEGS})
    figures = {"unbooked": D(0), "pause_reason": None,
               "positions": [{"contract_id": cid, "net_quantity": q, "instrument": kind.value, "strike": D(k),
                              "expiry": EXPIRY, "ltp": D(ltp)} for cid, kind, k, q, ltp in LEGS]}
    found = {cid: SimpleNamespace(feed_key=f"k{cid}") for cid, *_ in LEGS}
    return route._greeks(figures, found, snapshot, "NIFTY")


def test_paper_reply_on_expiry_day_carries_decay_left_today_per_leg_and_net():
    got = _paper(NOON)["greeks"]
    assert got is not None
    assert got["net"]["decay_left_today"] == D("100.75")
    assert got["net"]["decay_left_today_text"].startswith("Decay left today: ")
    assert "100.75" in got["net"]["decay_left_today_text"]
    assert [g["decay_left_today"] for g in got["legs"]] == [D("-201.50"), D("273.00"), D("68.25"), D("-39.00")]
    assert abs(D(got["net"]["theta"])) > D("1000")  # theta per day at the same instant: the figure it replaces


def test_paper_reply_on_another_day_has_no_decay_left_today():
    got = _paper(datetime.datetime(2026, 11, 24, 12, 30, tzinfo=IST))["greeks"]
    assert got["net"]["decay_left_today"] is None and got["net"]["decay_left_today_text"] is None
    assert all(g["decay_left_today"] is None for g in got["legs"])
    assert got["net"]["theta"] is not None
