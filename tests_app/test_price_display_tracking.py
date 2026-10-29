"""GC-UI D-PX (REQ-152 AC-2): the tracking leg carries two-decimal texts beside its exact prices (the Paper tab printed
"186.1" beside "187.35"). Pure function test, no database."""
from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace

from ofo.engine.legs import Action, Instrument
from ofo.tracking import paper

from ofo_app.routes.tracking import _figures

NOW = datetime.datetime(2026, 10, 29, 6, 0, tzinfo=datetime.UTC)


def test_the_tracking_leg_carries_two_decimal_price_texts() -> None:
    leg = paper.TrackedLeg(instrument_id="NSE_FO:1", action=Action.BUY, instrument=Instrument.CE, strike=Decimal("23000"),  # noqa: E501 - long line kept whole
                           expiry=datetime.date(2026, 11, 3), quantity=65, entry_price=Decimal("187.35"), price_at=NOW)
    tracking = SimpleNamespace(exits=[], exit_prices={})
    view = SimpleNamespace(legs=[SimpleNamespace(price=Decimal("186.1"), state="live", at=NOW)], leg_pnls=[None],
                           exited=False, paused=False, pause_reason=None, as_of=NOW, paper_pnl=None,
                           booked=Decimal("0"), unbooked=Decimal("0"))
    row = _figures(tracking, [leg], view, [None])["legs"][0]
    assert row["entry_price_display"] == "187.35"
    assert row["current_price_display"] == "186.10"
    assert row["exit_price_display"] is None


def test_the_tracking_reply_carries_the_servers_signed_text_of_each_total() -> None:
    """Live #603 item 1 (REQ-152 AC-4): the total / booked / unbooked texts come from the same template as each leg's
    pnl_text (U+2212 on a loss), so the panel never forms a sign of its own."""
    from ofo_app.routes.tracking import _view
    leg = paper.TrackedLeg(instrument_id="NSE_FO:1", action=Action.BUY, instrument=Instrument.CE, strike=Decimal("23000"),  # noqa: E501 - long line kept whole
                           expiry=datetime.date(2026, 11, 3), quantity=65, entry_price=Decimal("187.35"), price_at=NOW)
    tracking = SimpleNamespace(exits=[], exit_prices={}, strategy_id=1, started_at=NOW, prices_at=NOW)
    view = SimpleNamespace(legs=[SimpleNamespace(price=Decimal("186.1"), state="live", at=NOW)],
                           leg_pnls=[Decimal("-19.50")], exited=False, paused=False, pause_reason=None, as_of=NOW,
                           paper_pnl=Decimal("-19.50"), booked=Decimal("0.00"), unbooked=Decimal("-19.50"),
                           index=None, breakevens=None, detections=[])
    out = _view(tracking, [leg], "NIFTY", view, NOW, [None]).model_dump(mode="json")
    assert out["paper_pnl_text"] == "−19.50" == out["unbooked_text"] and out["booked_text"] == "0.00"
    assert out["legs"][0]["pnl_text"] == out["paper_pnl_text"]
