# ruff: noqa: PLC0415, PLR2004, F811
"""GC-SET step 5a (REQ-167 AC-4): the live sockets price with the risk-free rate in force at each tick, never the
feed's context captured when the Kite socket started (``live_market`` builds it with the registry default).

Spec basis: REQ-167 AC-4 "Each wired calculation reads the value in force when it runs (no restart)"; contract step 5
"the paper monitor (``feed.ctx.rate``) and the live chain socket re-read settings at their next tick".
No database, no Kite connection: the settings reader is replaced by an in-memory one whose rate the test changes.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

from ofo.settings import RISK_FREE_RATE, defaults
from test_strategy_live_push import (
    SELL_CE,
    ChannelClosed,
    outcome_route,
    request,
    rig,  # noqa: F401 - the fixture
    settle,
    tick,
)


def _rate_reader(monkeypatch, rate: list[str]) -> None:
    async def read():
        values = defaults()
        values[RISK_FREE_RATE] = Decimal(rate[0])
        return values

    monkeypatch.setattr(outcome_route, "_settings_in_force_now", read)


async def test_the_strategy_push_prices_each_tick_with_the_rate_in_force_then(rig, monkeypatch):
    from ofo_app import live_push

    rate = ["0.065"]
    _rate_reader(monkeypatch, rate)
    seen: list[Decimal] = []
    real = live_push.outcome_response

    def spy(req, ctx, *a, **k):
        seen.append(ctx.rate)
        return real(req, ctx, *a, **k)

    monkeypatch.setattr(live_push, "outcome_response", spy)
    provider, feed, channel, mono, push = rig
    task = asyncio.create_task(push.run())
    await channel.inbound.put(request(provider))
    await settle()
    rate[0] = "0.07"  # the admin saves 7% while the socket runs
    tick(provider, SELL_CE, "111.05")
    mono.now += 2.0
    await settle()
    await channel.inbound.put(ChannelClosed)
    await task
    assert seen[0] == Decimal("0.065") and seen[-1] == Decimal("0.07")
    assert feed.ctx.rate != Decimal("0.07")  # the feed's own start context is not what priced the second push


async def test_the_chain_greeks_refresh_reads_the_rate_in_force_at_that_refresh(monkeypatch):
    from ofo_app import chain_push
    from test_chain_live import close, index_quote, make_rig, start, tick_window

    rate = ["0.065"]

    async def read():
        values = defaults()
        values[RISK_FREE_RATE] = Decimal(rate[0])
        return values

    seen: list[Decimal] = []
    real = chain_push.model_of

    def spy(ctx, req, valuation):
        seen.append(ctx.rate)
        return real(ctx, req, valuation)

    monkeypatch.setattr(chain_push, "model_of", spy)
    provider, feed, channel, mono, push = make_rig(settings=read)
    provider.tick(index_quote("25162.30"))
    tick_window(provider)
    task = await start(push, channel)
    rate[0] = "0.07"
    mono.now += chain_push.OI_REFRESH_SECONDS
    tick_window(provider, ltp_offset=1)
    await settle()
    await close(channel, task)
    assert seen and seen[0] == Decimal("0.065") and seen[-1] == Decimal("0.07")
    assert feed.ctx.rate == Decimal("0.065")


async def test_a_chain_settings_read_that_fails_shows_no_greeks_rather_than_a_held_rate(monkeypatch):
    from ofo_app import chain_push
    from test_chain_live import close, index_quote, make_rig, start, tick_window

    reads: list[int] = []

    async def broken():  # the request's own read (strikes each side) answers; the Greeks refresh read fails
        reads.append(1)
        if len(reads) == 1:
            return defaults()
        raise RuntimeError("store down")

    calls: list[int] = []
    monkeypatch.setattr(chain_push, "model_of", lambda *a: calls.append(1))
    provider, _feed, channel, _mono, push = make_rig(settings=broken)
    provider.tick(index_quote("25162.30"))
    tick_window(provider)
    task = await start(push, channel)
    await close(channel, task)
    assert len(reads) >= 2 and channel.sent  # the refresh read was attempted and the chain still answered
    assert calls == []  # no model computed on any rate
    assert channel.sent[-1]["state"] == "NOT_CONNECTED" and channel.sent[-1]["rows"] == []  # no number shown
