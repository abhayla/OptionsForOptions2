"""REQ-133 AC-2 / AC-4 (W-152, row 24): every live push echoes the version (``seq``) of the follow message it was
computed for, through the one echo rule (``echo_seq``, the REST route's); no version sent -> no ``seq`` key (the old
behaviour). The browser half (an older-version push is dropped) is frontend/tests/strategy-live.test.js and
live-strategies.test.js. Runs on the recorded 2026-10-08 replay frames with a hand-moved monotonic clock."""
from __future__ import annotations

import asyncio

import test_strategy_live_push as base
from test_strategy_live_push import ERROR, SELL_CE, ChannelClosed, request, settle, tick

TWO_LOTS, THREE_LOTS, VERSION_SEVEN = 2, 3, 7
rig = base.rig  # the push file's replay rig (a pytest fixture), shared, not copied


def _versioned(provider, seq: int, lots: int = 1) -> dict:
    body = request(provider)
    for leg in body["legs"]:
        leg["lots"] = lots
    return {**body, "seq": seq}


async def test_pushes_echo_the_version_they_were_computed_for(rig):
    provider, _feed, channel, mono, push = rig
    task = asyncio.create_task(push.run())
    await channel.inbound.put(_versioned(provider, 1, lots=TWO_LOTS))
    await settle()
    assert [m["seq"] for m in channel.sent] == [1] and channel.sent[0]["legs"][0]["lots"] == TWO_LOTS
    await channel.inbound.put(_versioned(provider, 2, lots=THREE_LOTS))  # the user edits 2 -> 3 lots
    await settle()
    mono.now += 1.0  # the one-a-second gate (ADR-068)
    await settle()
    assert [m["seq"] for m in channel.sent] == [1, 2] and channel.sent[1]["legs"][0]["lots"] == THREE_LOTS
    tick(provider, SELL_CE, "41.05")  # a tick re-push keeps the version of the strategy it computes
    mono.now += 1.0
    await settle()
    assert [m["seq"] for m in channel.sent] == [1, 2, 2]
    await channel.inbound.put(ChannelClosed)
    await task


async def test_a_follow_message_without_a_version_gets_pushes_without_one(rig):
    provider, _feed, channel, _mono, push = rig
    task = asyncio.create_task(push.run())
    await channel.inbound.put(request(provider))
    await settle()
    assert len(channel.sent) == 1 and "seq" not in channel.sent[0]
    await channel.inbound.put(ChannelClosed)
    await task


async def test_a_bad_version_is_the_one_catalogue_message_and_the_socket_goes_on(rig):
    provider, _feed, channel, _mono, push = rig
    task = asyncio.create_task(push.run())
    for bad in ("1", -1, 1.5, True):
        await channel.inbound.put({**request(provider), "seq": bad})
    await channel.inbound.put(_versioned(provider, VERSION_SEVEN))
    await settle()
    assert channel.sent[:4] == [ERROR] * 4 and channel.sent[4]["seq"] == VERSION_SEVEN
    await channel.inbound.put(ChannelClosed)
    await task
