"""GC-UI D-PX (REQ-152 AC-2): the tracking leg carries two-decimal texts beside its exact prices (the Paper tab printed
"186.1" beside "187.35"). Pure function test, no database. Since GC-TP 1a part 4 the figures come from the paper order
book (one open order here) through the one engine."""
from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace

from ofo.engine.legs import Action, Instrument
from ofo.tracking import book, paper
from ofo.tracking.orderbook import PaperOrder
from ofo_app.routes.tracking import _Book, _figures, _view

NOW = datetime.datetime(2026, 10, 29, 6, 0, tzinfo=datetime.UTC)


def _one_open() -> tuple[_Book, paper.TrackedLeg]:
    orders = (PaperOrder("1", "BUY", 65, Decimal("187.35"), "open", NOW),)
    leg = paper.TrackedLeg(instrument_id="NSE_FO:1", action=Action.BUY, instrument=Instrument.CE,
                           strike=Decimal("23000"), expiry=datetime.date(2026, 11, 3), quantity=65,
                           entry_price=Decimal("187.35"), price_at=NOW)
    return _Book(1, orders, book.contract_legs(orders)), leg


def _live_view(**extra) -> SimpleNamespace:
    return SimpleNamespace(legs=[SimpleNamespace(price=Decimal("186.1"), state="live", at=NOW)], exited=False,
                           paused=False, pause_reason=None, as_of=NOW, **extra)


def test_the_tracking_leg_carries_two_decimal_price_texts() -> None:
    bk, leg = _one_open()
    row = _figures(bk, [leg], _live_view(), [None])["legs"][0]
    assert row["entry_price_display"] == "187.35"
    assert row["current_price_display"] == "186.10"
    assert row["exit_price_display"] is None


def test_the_tracking_reply_carries_the_servers_signed_text_of_each_total() -> None:
    """Live #603 item 1 (REQ-152 AC-4): the total / booked / unbooked texts come from the same template as each leg's
    pnl_text (U+2212 on a loss), so the panel never forms a sign of its own. (186.10 - 187.35) x 65 = -81.25."""
    bk, leg = _one_open()
    out = _view(bk, [leg], "NIFTY", _live_view(index=None, breakevens=None, detections=[]), NOW,
                [None]).model_dump(mode="json")
    assert out["paper_pnl_text"] == chr(0x2212) + "81.25" == out["unbooked_text"] and out["booked_text"] == "0.00"
    assert out["legs"][0]["pnl_text"] == out["paper_pnl_text"]
