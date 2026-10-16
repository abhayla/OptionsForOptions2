"""W-073 (REQ-035 AC-4; ADR-077; #234 item 2): `fallback` is the REST refresh's flag. The live socket refuses a message
that carries the key (any value) with the catalogue's input error, the same path as any other invalid message, and the
connection goes on. REST keeps accepting it. No database, no network."""
from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from test_strategy_live_push import ERROR, ChannelClosed, rig, request, settle, strategy_ids  # noqa: F401


@pytest.mark.parametrize("value", [True, False, None, "true", 0])
async def test_the_socket_refuses_a_message_with_a_fallback_key(rig, value):
    provider, feed, channel, mono, push = rig
    good = request(provider)
    before = provider.subscribed_tokens()  # the rig holds the recorded instruments (gate 4a D-1)
    task = asyncio.create_task(push.run())
    await channel.inbound.put({**good, "fallback": value})
    await settle()
    assert channel.sent == [ERROR]
    # nothing was subscribed for the refused message: no fan-out hold, provider tokens unchanged
    assert all(feed.fanout.subscriber_count(i) == 0 for i in strategy_ids(provider))
    assert provider.subscribed_tokens() == before
    await channel.inbound.put(good)  # the same strategy without the key is answered normally
    await settle()
    assert len(channel.sent) == 2 and channel.sent[1] != ERROR and "state" in channel.sent[1]
    await channel.inbound.put(ChannelClosed)
    await task


async def test_rest_still_accepts_fallback(rig):
    from ofo_app.main import create_app
    from ofo_app.routes.outcome import get_market_context

    provider, feed, channel, mono, push = rig
    app = create_app()
    app.dependency_overrides[get_market_context] = lambda: feed.ctx
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        for flag in (True, False):
            res = await ac.post("/api/strategies/outcome", json={**request(provider), "fallback": flag})
            assert res.status_code == 200, res.text
            assert "state" in res.json()
