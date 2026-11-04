"""GC-IC1 step 9 live fix: the adjustment chain rows carry the feed's open interest through the strike drawer's one
rule (``outcome_oi.oi_of``), so the Compare's OI limit is applied on the live chain. No database, no Kite.

Live 2026-11-04 10:49:44, strategy 82: A-01 / A-11 / A-06 read "OI not known" while the feed held OI 34515 on 23850 CE.
Cause: ``chain_rows`` never set ``ChainRow.oi``."""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from types import SimpleNamespace

from ofo.adjustment import liquidity
from ofo.rules.inputs import DataHealth
from ofo_app import adjustment_readers as readers
from ofo_app.outcome_oi import oi_of

EXPIRY = datetime.date(2026, 12, 29)
LIMITS = liquidity.limits_from_guards({"hide_oi_below": 500})
IID = "NFO:111"
LIVE_OI = 34515


def _listed():
    c = SimpleNamespace(strike=D("23850"), instrument_type="CE", expiry=EXPIRY, exchange_segment="NFO",
                        exchange_token="111")  # noqa: S106 - an instrument token, not a password
    return [SimpleNamespace(contract=c, broker_refs=[SimpleNamespace(broker_symbol="NIFTY23850CE")])]


def _quote(oi, health=DataHealth.AVAILABLE, ltp="120.5"):
    return SimpleNamespace(instrument_id=IID, ltp=D(ltp), bid=D("120"), ask=D("121"), oi=oi, health=health,
                           timestamp=datetime.datetime(2026, 11, 3, 10, 0, tzinfo=datetime.UTC),
                           validation_errors=(), source=SimpleNamespace(declared_delay_seconds=0))


def _row(quote, closed=False):
    quotes = {} if quote is None else {IID: quote}
    rows, _ids, _g = readers.chain_rows(_listed(), EXPIRY, quotes, lambda _i, _q: None, None, closed)
    assert len(rows) == 1
    return rows[0]


def _state(row):
    return liquidity.evaluate_strike(LIMITS, getattr(row, "oi", None), row.bid, row.ask)


def test_live_oi_34515_is_carried_and_not_flagged_unknown():
    row = _row(_quote(LIVE_OI))
    assert row.oi == LIVE_OI
    assert _state(row).oi == "ok" and liquidity.FLAG_OI_UNKNOWN not in _state(row).flags


def test_oi_300_below_the_limit_is_flagged_below():
    state = _state(_row(_quote(300)))
    assert state.oi == "below" and liquidity.FLAG_BELOW in state.flags


def test_no_quote_reads_oi_not_known():
    row = _row(None)
    assert row.oi is None and liquidity.FLAG_OI_UNKNOWN in _state(row).flags


def test_unavailable_book_in_hours_reads_oi_not_known():
    row = _row(_quote(LIVE_OI, health=DataHealth.STALE))
    assert row.oi is None and liquidity.FLAG_OI_UNKNOWN in _state(row).flags


def test_market_closed_follows_the_drawers_rule_not_a_raw_read():
    """oi_of's closed branch needs a real quote for price_counts; the stale-health quote is read raw by the
    closed branch only if the last close counts, so the row must equal oi_of exactly."""
    for q in (_quote(LIVE_OI, health=DataHealth.STALE), _quote(LIVE_OI, ltp="0"), _quote(LIVE_OI)):
        assert _row(q, closed=True).oi == oi_of(q, True)
    assert _row(_quote(LIVE_OI, ltp="0"), closed=True).oi is None  # no last close held: not known, never 0
