"""User test 2026-10-30 (U18; ADR-200 (2), ADR-212): the Option Chain cell's one gate (`chain_push._greek_fields`)
shows IV from a sound held close only when the market is closed; in hours a STALE price is old, and an UNHEALTHY quote
never counts. Moved from tests/test_chain_model.py (that folder may not import ofo_app). No database needed.

Inputs: the 2026-10-08 09:20:09 IST recorded NIFTY cell (22500 CE LTP 151.30, spot 22,533.25), as in
tests/test_chain_model.py.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from ofo.engine.chain_values import chain_model
from ofo.engine.legs import Instrument
from ofo.marketdata.quote import NormalizedQuote, SourceMetadata
from ofo.rules.inputs import DataHealth
from ofo_app.chain_push import _greek_fields

D = Decimal
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
VALUATION = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)
EXPIRY = datetime.date(2026, 10, 13)
RATE = D("0.065")
CE_ID = "NSE_FO:44612"


def _quote(instrument_id: str, kind: Instrument | None, strike: str | None, ltp: str,
           health: DataHealth) -> NormalizedQuote:
    segment = "NSE_FO" if kind is not None else "INDICES"
    return NormalizedQuote(instrument_id, "NIFTY", "NSE", segment, kind, None if kind is None else EXPIRY,
                           None if strike is None else D(strike), D(ltp), None, None, *([None] * 8),
                           VALUATION, SourceMetadata("recorded", "kite-2026-10-08"), health)


def test_u18_a_cell_shows_iv_from_a_sound_stale_close_only_when_closed():
    spot = _quote("NSE_INDEX:256265", None, None, "22533.25", DataHealth.STALE)
    stale_ce = _quote(CE_ID, Instrument.CE, "22500", "151.30", DataHealth.STALE)
    model = chain_model([stale_ce], spot, EXPIRY, VALUATION, RATE, market_closed=True)
    assert _greek_fields(stale_ce, model, CE_ID, market_closed=True)["iv"] is not None
    assert _greek_fields(stale_ce, model, CE_ID, market_closed=False)["iv"] is None  # in hours a STALE price is old
    unhealthy = _quote(CE_ID, Instrument.CE, "22500", "151.30", DataHealth.UNHEALTHY)
    assert _greek_fields(unhealthy, model, CE_ID, market_closed=True)["iv"] is None
