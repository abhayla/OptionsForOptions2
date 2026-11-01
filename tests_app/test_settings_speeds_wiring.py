# ruff: noqa: PLC0415, PLC0414, PLR0402, PLR2004, RUF059, E501, F811
"""GC-SET batch 2 (REQ-166 AC-1, REQ-167 AC-4): ``speeds.open_strategy_seconds`` is read from the settings in force at
each tick of the live push, and the three carried fixes of the step 3 review (one settings read per request; a bad
cross-field admin value refused at SAVE time and never a user 422; a bad range refused on every answer branch and at
the live follow message).

Spec basis: REQ-166 AC-1 "a strategy open on a screen at most once a second" (the number is the setting); REQ-167 AC-4
"each wired calculation reads the value in force when it runs (no restart); a test per setting".
No Kite connection; the database tests use the rolled-back connection pattern of ``test_settings_calc_wiring.py``.
"""
from __future__ import annotations

import asyncio
import pathlib
from decimal import Decimal
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient
from ofo.errors import render
from ofo.settings import defaults
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_settings_rate_wiring import _body, _live
from test_settings_rate_wiring import replayed as replayed
from test_strategy_live_push import (
    SELL_CE,
    ChannelClosed,
    outcome_route,
    request,
    rig,  # noqa: F401 - the fixture
    settle,
    tick,
)

KEY = "speeds.open_strategy_seconds"


def _reader(monkeypatch, seconds: list[str]):
    """The settings reader the push calls at each tick: ``seconds[0]`` is the setting in force now (mutable)."""

    async def read():
        values = defaults()
        values[KEY] = Decimal(seconds[0])
        return values

    monkeypatch.setattr(outcome_route, "_settings_in_force_now", read)


async def _pushes(rig, gaps: list[float]) -> int:
    """Open the strategy, then per gap: one changed tick and the monotonic clock moves by the gap; the pushes sent."""
    provider, feed, channel, mono, push = rig
    task = asyncio.create_task(push.run())
    await channel.inbound.put(request(provider))
    await settle()
    for n, gap in enumerate(gaps):
        tick(provider, SELL_CE, f"{100 + n}.05")
        mono.now += gap
        await settle()
    await channel.inbound.put(ChannelClosed)
    await task
    return len(channel.sent)


async def test_core_the_setting_one_pushes_every_second(rig, monkeypatch):
    _reader(monkeypatch, ["1"])
    assert await _pushes(rig, [1.0] * 4) == 5  # the baseline and one push per changed second


def _fresh_rig():
    from test_strategy_live_push import (
        RATE,
        VALUATION,
        FakeChannel,
        FanOut,
        LiveFeed,
        MarketContext,
        Mono,
        StrategyPush,
        held_replay,
        new_provider,
    )

    provider, clock, items = new_provider()
    held_replay(provider, clock, items)
    feed = LiveFeed(MarketContext(provider, lambda: VALUATION, RATE), FanOut(provider))
    channel, mono = FakeChannel(), Mono()
    return provider, feed, channel, mono, StrategyPush(channel, feed, monotonic=mono, poll=0.005)


async def test_core_the_setting_two_halves_the_pushes(monkeypatch):
    """Same code, same ticks, same clock as the test above: only the stored setting differs (2 instead of 1)."""
    _reader(monkeypatch, ["2"])
    assert await _pushes(_fresh_rig(), [1.0] * 4) == 3  # the baseline and a push every second changed tick


async def test_a_changed_interval_applies_at_the_next_tick_with_no_restart(rig, monkeypatch):
    seconds = ["2"]
    _reader(monkeypatch, seconds)
    provider, feed, channel, mono, push = rig
    task = asyncio.create_task(push.run())
    await channel.inbound.put(request(provider))
    await settle()
    assert len(channel.sent) == 1  # this push read 2
    seconds[0] = "1"  # the admin saves 1 while the socket runs
    tick(provider, SELL_CE, "111.05")
    mono.now += 2.0
    await settle()
    assert len(channel.sent) == 2  # this push read 1
    tick(provider, SELL_CE, "112.05")
    mono.now += 1.0
    await settle()
    assert len(channel.sent) == 3  # allowed after 1 s; with the old value 2 it would not be
    await channel.inbound.put(ChannelClosed)
    await task


def test_no_literal_push_interval_is_left_in_the_push_modules():
    import re

    import ofo_app.live_push as live_push

    assert not hasattr(live_push, "MIN_PUSH_INTERVAL")
    app = pathlib.Path(live_push.__file__).parent
    for name in ("live_push.py", "chain_push.py", "index_push.py"):
        src = (app / name).read_text(encoding="utf-8")
        assert "MIN_PUSH_INTERVAL" not in src, name
    assert not re.search(r"(?<![\w.])1\.0(?![\w.])", (app / "live_push.py").read_text(encoding="utf-8"))


async def test_the_chain_and_indices_sockets_read_the_same_setting_at_their_ticks(monkeypatch):
    from ofo_app.live_push import PushInterval

    seconds = ["3"]
    _reader(monkeypatch, seconds)
    now = [0.0]
    interval = PushInterval(lambda: now[0])
    assert await interval.current() == 3.0
    seconds[0] = "1"
    assert await interval.current() == 3.0  # inside the interval last read: no new read yet
    now[0] = 3.0
    assert await interval.current() == 1.0  # the next tick after it: the new value, no restart


# ---- carried fix c: a bad range is refused where the request arrives ---------------------------------------------------
async def test_a_bad_payoff_step_is_refused_at_the_follow_message_not_at_every_tick(rig):
    provider, feed, channel, mono, push = rig
    task = asyncio.create_task(push.run())
    await channel.inbound.put(dict(request(provider), payoff_step=7))
    await settle()
    assert channel.sent == [render("user_input_request_invalid").as_dict()]
    tick(provider, SELL_CE, "120.05")
    mono.now += 5.0
    await settle()
    assert len(channel.sent) == 1 and push._handle is None  # nothing subscribed
    await channel.inbound.put(ChannelClosed)
    await task


async def test_a_bad_payoff_step_is_a_422_on_the_waiting_first_price_branch_too(rig, monkeypatch):
    """Carried fix c: with a live context still waiting for its first price frame, ``checked_choice`` used to be skipped."""
    from fastapi.exceptions import RequestValidationError
    from ofo_app.routes.outcome import OutcomeRequest, outcome_response
    from test_strategy_live_push import VALUATION

    provider, feed, channel, mono, push = rig
    monkeypatch.setattr(outcome_route, "awaiting_first_price_for", lambda *_a, **_k: True)
    req = OutcomeRequest.model_validate(dict(request(provider), payoff_step=7))
    with pytest.raises(RequestValidationError):
        outcome_response(req, feed.ctx, settings=defaults())
    good = OutcomeRequest.model_validate(request(provider))
    assert outcome_response(good, feed.ctx, settings=defaults()).state is not None
    assert VALUATION  # the rig's clock


def test_a_bad_stored_combination_is_a_server_fault_not_a_user_422():
    """Carried fix b: step 150 with anchor 100 is the admin's fault; the user's request must not get a 422 for it."""
    from fastapi.exceptions import RequestValidationError
    from ofo_app.routes.outcome import OutcomeRequest, checked_choice

    values = defaults()
    values["scenarios.nifty_step_points"] = Decimal("150")
    req = OutcomeRequest.model_validate({"underlying": "NIFTY", "legs": [
        {"instrument_id": SELL_CE, "action": "SELL", "lots": 1, "planned_entry": "1.00",
         "captured_at": "2026-10-08T09:20:09+05:30"}]})
    with pytest.raises(ValueError) as caught:
        checked_choice(req, values)
    assert not isinstance(caught.value, RequestValidationError)


async def test_a_cross_field_break_is_refused_when_the_admin_saves_it(app_engine: AsyncEngine):
    """Carried fix b (structural): the save is refused with a reason; nothing is stored."""
    from ofo.settings import SettingRefused
    from ofo_app import settings_store

    conn = await app_engine.connect()
    trans = await conn.begin()
    try:
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
        with pytest.raises(SettingRefused) as caught:
            await settings_store.add_setting(session, "scenarios.nifty_step_points", "150", set_by="admin-test",
                                             correlation_id="b2-cross-1")
        assert caught.value.code == "setting_cross_field" and "NIFTY" in caught.value.reason
        assert (await settings_store.settings_in_force(session))["scenarios.nifty_step_points"] == Decimal("100")
        await settings_store.add_setting(session, "scenarios.nifty_step_points", "200", set_by="admin-test",
                                         correlation_id="b2-cross-2")  # a multiple of the anchor 100: accepted
    finally:
        await trans.rollback()
        await conn.close()


# ---- carried fix a: one settings read per request ---------------------------------------------------------------------
async def test_one_request_makes_one_settings_read(replayed, monkeypatch):
    from ofo_app.main import create_app
    from ofo_app.routes.outcome import get_settings_reader

    _live(replayed, monkeypatch)
    reads: list[int] = []

    async def read():
        reads.append(1)
        return defaults()

    app = create_app()
    app.dependency_overrides[get_settings_reader] = lambda: read
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/strategies/outcome", json=_body(replayed))
        assert resp.status_code == HTTPStatus.OK, resp.text
        assert len(reads) == 1  # the live context and the calculation shared one read
        await ac.post("/api/strategies/outcome", json=_body(replayed))
        assert len(reads) == 2  # the next request reads again (no restart, no cache across requests)
