"""GC-UI F-5 (ADR-172, ADR-197): a stale quote is not a live side, so its IV comes from the LTP / closing price.

ADR-172: a leg's IV "is implied from its bid-ask mid when both the bid and the ask are live and the ask is at or above
the bid; otherwise from its last traded price (LTP) where one exists". ADR-197: after hours every number is "computed
by the engine from the closing prices and the closing-price IV". A bid / ask on a STALE (or any not-AVAILABLE) quote is
a book that stopped ticking, not a live side - so the engine's one IV price (:func:`ofo.engine.model.iv_price`) is the
LTP there, never the stale mid.

The core is the REAL recorded reply ``tests/fixtures/ui_data_check/closed_s54/`` (strategy 54, 2026-10-28 17:13 IST,
market closed): leg NIFTY26N0322600CE LTP 237.90, stale bid 237.65 / ask 239.25 (stale mid 238.45); the old server
showed IV 0.147800 there, the IV of the stale mid at q = 0 (spot fallback forward). Every expected IV below is solved by
the engine's own IV call at the same inputs, never typed.
"""
from __future__ import annotations

import dataclasses
import datetime
import json
from decimal import Decimal
from pathlib import Path

import pytest
from ofo.engine.chain_values import chain_greeks
from ofo.engine.legs import Instrument
from ofo.engine.model import iv_price
from ofo.marketdata.quote import NormalizedQuote, SourceMetadata
from ofo.rules.inputs import DataHealth

D = Decimal
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ui_data_check" / "closed_s54"
RATE = D("0.065")  # the server's rate (ofo_app.live_market.LIVE_RATE)


def _reply():
    return json.loads((FIXTURE / "outcome_estimated_now.json").read_text(encoding="utf-8"))


def _leg_quote(symbol: str) -> tuple[NormalizedQuote, NormalizedQuote, dict, datetime.datetime]:
    """(the leg's quote as the server held it, the spot quote, the recorded leg row, the valuation) from the reply."""
    reply = _reply()
    leg = next(x for x in reply["legs"] if x["symbol"] == symbol)
    book = next(x for x in reply["leg_quotes"] if x["symbol"] == symbol)
    valuation = datetime.datetime.fromisoformat(reply["valuation"])
    src = SourceMetadata("recorded", "closed_s54-2026-10-28")
    q = NormalizedQuote(leg["instrument_id"], "NIFTY", "NSE", "NSE_FO", Instrument(leg["instrument"]),
                        datetime.date.fromisoformat(leg["expiry"]), D(leg["strike"]), D(leg["ltp"]), D(book["bid"]),
                        D(book["ask"]), *([None] * 8), valuation, src, DataHealth(book["health"]))
    spot = NormalizedQuote("INDEX", "NIFTY", "NSE", "INDICES", None, None, None, D(reply["spot_level"]),
                           *([None] * 10), valuation, src, DataHealth.STALE)
    return q, spot, leg, valuation


def _engine_iv(q: NormalizedQuote, spot: NormalizedQuote, valuation: datetime.datetime) -> Decimal | None:
    g = chain_greeks([q], spot, q.expiry, valuation, RATE).get(q.instrument_id)
    return None if g is None else g.iv


def test_core_closed_s54_stale_leg_iv_is_implied_from_the_ltp_not_the_stale_mid():
    """The core proof on the real reply: the engine's IV source for the stale 22600 CE is its LTP 237.90, and its IV
    is the LTP-implied figure. Anchor: the same book marked live gives the old server's 0.147800 (the mid IV)."""
    q, spot, leg, valuation = _leg_quote("NIFTY26N0322600CE")
    assert (q.ltp, q.bid, q.ask, q.health) == (D("237.9"), D("237.65"), D("239.25"), DataHealth.STALE)
    assert iv_price(q) == D("237.9")
    live_book = dataclasses.replace(q, health=DataHealth.AVAILABLE)
    assert iv_price(live_book) == D("238.45")
    assert _engine_iv(live_book, spot, valuation) == D(leg["iv"]) == D("0.147800")  # the old server = the mid IV
    ltp_only = dataclasses.replace(q, bid=None, ask=None, health=DataHealth.AVAILABLE)  # the engine's solver on 237.90
    expected = _engine_iv(ltp_only, spot, valuation)
    assert expected is not None and expected != D(leg["iv"])
    assert _engine_iv(q, spot, valuation) == expected


def test_closed_s54_every_stale_leg_takes_its_ltp():
    """The class on the real reply: both legs of strategy 54 are stale after hours; each solves from its LTP."""
    for symbol in ("NIFTY26N0322600CE", "NIFTY26N0322800CE"):
        q, spot, _leg, valuation = _leg_quote(symbol)
        assert q.health is DataHealth.STALE and q.bid and q.ask and q.ask >= q.bid
        assert iv_price(q) == q.ltp, symbol
        ltp_only = dataclasses.replace(q, bid=None, ask=None, health=DataHealth.AVAILABLE)
        assert _engine_iv(q, spot, valuation) == _engine_iv(ltp_only, spot, valuation), symbol


def _q(ltp, bid, ask, health=DataHealth.AVAILABLE, kind=Instrument.CE):
    base, _spot, _leg, _v = _leg_quote("NIFTY26N0322600CE")
    strike = None if kind is Instrument.FUT else base.strike
    return dataclasses.replace(base, instrument_type=kind, strike=strike, ltp=None if ltp is None else D(ltp),
                               bid=None if bid is None else D(bid), ask=None if ask is None else D(ask), health=health)


@pytest.mark.parametrize(("ltp", "bid", "ask", "health", "expected"), [
    ("237.90", "237.65", "239.25", DataHealth.AVAILABLE, "238.45"),  # both sides live: the mid
    ("237.90", "237.65", "239.25", DataHealth.STALE, "237.90"),      # both sides stale: the LTP
    ("237.90", "237.65", "239.25", DataHealth.DELAYED, "237.90"),    # a delayed book is not live either
    ("237.90", "237.65", "239.25", DataHealth.UNHEALTHY, "237.90"),
    ("237.90", "237.65", "239.25", DataHealth.UNAVAILABLE, "237.90"),
    ("237.90", None, "239.25", DataHealth.STALE, "237.90"),          # one side missing, the other stale: the LTP
    ("237.90", "0", "239.25", DataHealth.AVAILABLE, "237.90"),       # one side not live (0), one live: the LTP
    (None, "237.65", "239.25", DataHealth.STALE, None),              # stale book and no LTP: no IV price
])
def test_iv_price_answer_states(ltp, bid, ask, health, expected):
    """Answer states: both live (mid), one side not live, both stale (LTP), no LTP (no IV price)."""
    assert iv_price(_q(ltp, bid, ask, health)) == (None if expected is None else D(expected))


def test_stale_book_without_ltp_gets_no_iv_from_the_picker():
    """No LTP: the picker solves nothing for the contract (no guessed IV from a stale mid)."""
    _base, spot, _leg, valuation = _leg_quote("NIFTY26N0322600CE")
    assert _engine_iv(_q(None, "237.65", "239.25", DataHealth.STALE), spot, valuation) is None


def test_futures_leg_gets_no_iv():
    """A FUT leg has no IV, whatever its book: the picker never solves one."""
    _base, spot, _leg, valuation = _leg_quote("NIFTY26N0322600CE")
    fut = _q("22750", "22740", "22760", DataHealth.STALE, Instrument.FUT)
    assert _engine_iv(fut, spot, valuation) is None

