"""AF-01 (owner PC 27 Nov), ADR-330 (36), ADR-212: after the close the leg picker's price for a strike first seen AFTER
the close is its first post-close frame and never moves. Drives the picker's own read (``strikes_answer``) over a real
``KiteProvider`` replaying the recorded 8 Oct session, then two REAL packets for one strike arriving after 15:30:
99.60 at 15:31:10, 100.10 at 15:33:48 (the sequence of the owner's 26 Nov check)."""
from __future__ import annotations

import datetime
import pathlib
import struct
import sys
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tests" / "marketdata"))
from _kite_fixture import NIFTY_CE_ID, all_instrument_ids, new_provider, replay
from ofo.marketdata.fanout import FanOut
from ofo_app.catalogue_picker import PickableContract
from ofo_app.chain_push import ChainCatalogue
from ofo_app.live_push import LiveFeed
from ofo_app.routes import leg_picker
from ofo_app.routes.leg_picker import strikes_answer
from ofo_app.routes.outcome import MarketContext

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
EXPIRY = datetime.date(2026, 10, 13)
DAY = datetime.date(2026, 10, 8)  # Thursday, a trading day
TOKEN = 11421186  # NSE_FO:44614, the Kite token of NIFTY 22550 CE in the catalogue fixture


def _at(h: int, m: int, s: int) -> datetime.datetime:
    return datetime.datetime(DAY.year, DAY.month, DAY.day, h, m, s, tzinfo=IST)


def _packet(token: int, ltp: str, ts: datetime.datetime) -> bytes:
    paise = int(Decimal(ltp) * 100)
    head = struct.pack(">11i", token, paise, 65, paise, 0, 0, 0, 0, 0, 0, 0)
    rest = struct.pack(">5i", 0, 1000, 0, 0, int(ts.timestamp()))
    level = struct.pack(">iihh", 65, paise - 5, 1, 0)
    ask = struct.pack(">iihh", 65, paise + 5, 1, 0)
    empty = b"\x00" * 12
    body = head + rest + level + empty * 4 + ask + empty * 4
    return (1).to_bytes(2, "big") + len(body).to_bytes(2, "big") + body


def _cell(out):
    row = next(r for r in out.rows if r.ce is not None and r.ce.instrument_id == NIFTY_CE_ID)
    return row.ce


def test_picker_shows_the_first_post_close_frame_of_a_new_strike_both_times():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    provider.book.remove(NIFTY_CE_ID)  # this strike has no frame of the session: first seen after the close
    feed = LiveFeed(MarketContext(provider, clock, Decimal("0.065")), FanOut(provider))

    def pick(lc) -> PickableContract:
        c = lc.contract
        return PickableContract(0, f"{c.exchange_segment}:{c.exchange_token}", c.exchange_segment, c.exchange_token,
                                c.instrument_type, c.expiry, c.strike, c.lot_size, "x")

    cat = ChainCatalogue(expiries=(EXPIRY,), contracts=tuple(
        pick(lc) for lc in items if lc.contract.name == "NIFTY" and lc.contract.instrument_type in ("CE", "PE")
        and lc.contract.expiry == EXPIRY))
    seen = []
    try:
        for ltp, at in (("99.60", _at(15, 31, 10)), ("100.10", _at(15, 33, 48))):
            clock.now = at
            provider.on_frame(_packet(TOKEN, ltp, at), at)
            clock.now = at + datetime.timedelta(seconds=5)
            seen.append(_cell(strikes_answer(feed, "NIFTY", EXPIRY, 10, cat, lambda: clock.now)))
    finally:
        leg_picker.LEASE.release()
    assert [(c.ltp, c.at) for c in seen] == [(Decimal("99.60"), _at(15, 31, 10))] * 2
