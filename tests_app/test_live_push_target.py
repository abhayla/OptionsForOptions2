"""GC-LIVE R-26 (REQ-084 AC-1/AC-4, ADR-209; ADR-068): the live follow message carries the what-if target, so every push
carries the target block the REST route would answer for the same pick and snapshot (one engine, ADR-008).

Seen live 30 Oct 2026 (ofo_dev, strategies 48 and 56): only the REST request carried the pick; a push (about once a
second) cancelled that request and, carrying no figures, marked the last ones "Stale", so a pick froze or was never
answered. Same rig as tests_app/test_strategy_live_push.py (the 2026-10-08 replay, a fake clock). No database: the
booked P&L reader is a fake, as in tests_app/test_outcome_target_booked.py.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

import test_strategy_live_push as base
from httpx import ASGITransport, AsyncClient
from ofo_app.live_push import ChannelClosed, StrategyPush
from ofo_app.main import create_app
from ofo_app.routes.outcome import get_booked_reader, get_market_context

rig = base.rig  # the shared fixture (the replay provider, fan-out, fake channel and clock)
SELL_CE, request, settle, tick = base.SELL_CE, base.request, base.settle, base.tick

LEVEL = "23000"
FIGURES = ("estimate", "exact")
MOVES = 3  # price moves after the first push


def _booked_reader(amount: Decimal | None, seen: list):
    async def read(strategy_id: int) -> Decimal | None:
        seen.append(strategy_id)
        return amount
    return read


async def _rest(feed, body: dict, reader=None) -> dict:
    app = create_app()
    app.dependency_overrides[get_market_context] = lambda: feed.ctx
    if reader is not None:
        app.dependency_overrides[get_booked_reader] = lambda: reader
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        return (await ac.post("/api/strategies/outcome", json=body)).json()


async def _first_push(channel, push, body: dict) -> asyncio.Task:
    task = asyncio.create_task(push.run())
    await channel.inbound.put(body)
    await settle()
    return task


async def _close(channel, task) -> None:
    await channel.inbound.put(ChannelClosed)
    await task


async def test_a_follow_with_a_target_level_pushes_the_target_figures_equal_to_rest(rig):
    provider, feed, channel, _mono, push = rig
    body = {**request(provider), "target_level": LEVEL}
    task = await _first_push(channel, push, body)
    assert channel.sent[0]["target"]["kind"] in FIGURES  # figures for the pick, not the limits alone
    assert channel.sent[0]["target"]["pnl"] is not None
    assert channel.sent[0] == await _rest(feed, body)  # the push IS the REST answer for the same pick and snapshot
    await _close(channel, task)


async def test_every_later_push_still_carries_the_target_figures(rig):
    provider, _feed, channel, mono, push = rig
    task = await _first_push(channel, push, {**request(provider), "target_level": LEVEL})
    for n in range(MOVES):  # three price moves one second apart: three re-pushes, each with figures for the pick
        tick(provider, SELL_CE, f"{120 + n}.05")
        mono.now += 1.0
        await settle()
    assert len(channel.sent) == 1 + MOVES
    assert all(m["target"]["kind"] in FIGURES for m in channel.sent)
    assert len({m["legs"][0]["ltp"] for m in channel.sent}) == 1 + MOVES  # each push was computed on the moved price
    await _close(channel, task)


async def test_a_follow_without_a_target_pushes_the_limits_alone_as_before(rig):
    provider, feed, channel, _mono, push = rig
    task = await _first_push(channel, push, request(provider))
    assert channel.sent[0]["target"].get("kind") is None  # nothing picked: the push is unchanged (limits only)
    assert channel.sent[0] == await _rest(feed, request(provider))
    await _close(channel, task)


async def test_a_paper_pick_reads_booked_with_the_rest_reader_and_equals_rest(rig):
    provider, feed, channel, mono, _ = rig
    seen: list = []
    reader = _booked_reader(Decimal("962.00"), seen)
    push = StrategyPush(channel, feed, monotonic=mono, poll=0.005, booked_reader=reader)
    body = {**request(provider), "target_level": LEVEL, "paper_strategy_id": 63}
    task = await _first_push(channel, push, body)
    assert seen == [63]  # the push read the strategy's booked P&L, once for its one push
    rest = await _rest(feed, body, reader)
    assert channel.sent[0]["target"] == rest["target"]  # booked rides on the push exactly as on REST
    await _close(channel, task)


async def test_switch_off_and_an_unreadable_book_match_rest(rig):
    provider, feed, channel, mono, _ = rig
    legs = request(provider)  # read while the replay still holds the legs (a closed socket releases them)
    for amount, extra in ((Decimal("962.00"), {"include_booked": False}), (None, {})):
        seen: list = []
        reader = _booked_reader(amount, seen)
        channel.sent.clear()
        push = StrategyPush(channel, feed, monotonic=mono, poll=0.005, booked_reader=reader)
        body = {**legs, "target_level": LEVEL, "paper_strategy_id": 63, **extra}
        task = await _first_push(channel, push, body)
        assert channel.sent[0]["target"]["kind"] in FIGURES
        assert seen == ([] if extra else [63])  # switch off: the book is not read at all
        assert channel.sent[0]["target"] == (await _rest(feed, body, reader))["target"]
        await _close(channel, task)
