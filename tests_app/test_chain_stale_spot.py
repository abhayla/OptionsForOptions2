"""W-124 fix round 1 (REQ-087 AC-2, REQ-049, ADR-015): a stale or delayed index quote never feeds a spot-based value.

RCA: ``live_spot`` checked only price > 0, so a STALE index quote at 25162.30 gave in_the_money / intrinsic /
time value /
breakeven % / ATM from the old price. Class: every chain value derived from the spot. By hand: spot 25162.30, call 25050
LTP 131.00 -> with an AVAILABLE spot intrinsic 112.30 and in the money; with a STALE or DELAYED spot every one is None,
the answer still LIVE, spot_health says why and spot_label is the catalogue's "stale since HH:MM IST".
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from ofo.marketdata.fanout import FanOut
from ofo.rules.inputs import DataHealth
from ofo_app.chain_push import ChainRequest
from ofo_app.routes.chain import chain_read
from ofo_app.routes.outcome import MarketContext
from test_chain_live import T0, Clock, FakeProvider, _catalogue, cid, index_quote, option_quote, request, tick_window

SPOT_KEYS = ("in_the_money", "intrinsic", "time_value", "breakeven_pct")


def _read(health: DataHealth):
    provider = FakeProvider()
    provider.tick(index_quote("25162.30", health=health))
    tick_window(provider)
    provider.tick(option_quote(cid("25050", "CE"), "131.00"))
    ctx = MarketContext(provider, Clock(T0), Decimal("0.065"))
    fanout = FanOut(provider)
    streaming = lambda i: True  # noqa: E731 - every shown input is held
    streaming.ctx = ctx
    req = ChainRequest.model_validate(request())
    return chain_read(ctx, streaming, req, _catalogue(), fallback=False, now=Clock(T0)), fanout


def _call_25050(body):
    return next(r.ce for r in body.rows if r.strike == Decimal("25050"))


def test_an_available_spot_feeds_the_values():
    body, _ = _read(DataHealth.AVAILABLE)
    cell = _call_25050(body)
    assert (cell.in_the_money, cell.intrinsic, cell.time_value) == (True, Decimal("112.30"), Decimal("18.70"))
    assert body.atm_strike == Decimal("25150") and body.spot_label is None


@pytest.mark.parametrize("health", [DataHealth.STALE, DataHealth.DELAYED])
def test_a_stale_or_delayed_spot_turns_every_spot_based_value_off_with_the_reason(health):
    body, _ = _read(health)
    assert body.state == "LIVE" and body.spot_health == health.value and body.spot == Decimal("25162.30")
    cells = [c for r in body.rows for c in (r.ce, r.pe) if c is not None]
    assert cells and all(getattr(c, k) is None for c in cells for k in SPOT_KEYS)
    assert body.atm_strike is None  # the ATM marker is spot-based too
    assert "IST" in str(body.spot_label)  # the catalogue's data label ("stale since HH:MM IST" / "delayed, as of ...")
    # values that do not need the spot stay: the price-only ones
    assert _call_25050(body).per_lot == Decimal("9825.00") and _call_25050(body).breakeven == Decimal("25181.00")
