"""D-01 (25 Nov 2026), ADR-327: saving a paper trigger reads the live price it is compared with, ASKING the feed.

Spec basis: ADR-317 (1) (a level the live price has already crossed is refused); ADR-327 (market open and no live price
after asking the feed and waiting up to 3 s: refused with "Not saved: the live price could not be read, so this level
cannot be checked. Try again in a moment."; market closed: saved, arms at the next live tick).

Core: "Above 22,500" with NIFTY at 22,533.25 is refused even when nothing else in the process holds the index. The
replay is the recorded Kite frames of 2026-10-08 09:20 IST through a real ``KiteProvider`` and a real ``FanOut``; in bus
mode the API's provider drops every tick for a token nobody holds (``kite_provider.py`` ``on_frame``), so the frames are
pushed only AFTER the hold has subscribed (``d01-root-cause.md`` section 5). The 3 s wait is an injected sleep and
clock: no test sleeps, and no test reads the wall clock. No database: ``tracked_contracts.resolve`` is the only DB
touch and is stubbed.
"""
from __future__ import annotations

import datetime
import pathlib
import sys
from decimal import Decimal
from types import SimpleNamespace

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from marketdata._kite_fixture import NIFTY_CE_ID, all_instrument_ids, new_provider, recorded_frames  # noqa: E402
from ofo.errors.templates import render  # noqa: E402
from ofo.marketdata.fanout import FanOut  # noqa: E402
from ofo_app import paper_trigger_store, tracked_contracts  # noqa: E402
from ofo_app.live_push import POLL_SECONDS, LiveFeed  # noqa: E402
from ofo_app.market_read import Wait  # noqa: E402
from ofo_app.routes import paper as paper_routes  # noqa: E402
from ofo_app.routes.outcome import MarketContext  # noqa: E402

D = Decimal
CROSSED, LEG_CROSSED = "paper_trigger_already_crossed", "paper_trigger_leg_already_crossed"
UNREADABLE = "paper_trigger_price_unreadable"
SPOT = D("22533.25")  # the recorded NIFTY at the last frame (repro_d01)
LEG_ID = NIFTY_CE_ID  # NSE_FO:44614
LEG_CONTRACT = 7
WAIT_S = 3.0
VERBATIM = "Not saved: the live price could not be read, so this level cannot be checked. Try again in a moment."


class Rig:
    """A connected provider that holds nothing, the recorded frames to push later, and the injected wait."""

    def __init__(self) -> None:
        self.provider, self.clock, self.items = new_provider()
        self.frames = recorded_frames()
        self.provider.on_connected(self.frames[0][0])  # connected; no frame yet; nothing subscribed
        self.ctx = MarketContext(self.provider, self.clock, D("0.065"))
        self.feed = LiveFeed(self.ctx, FanOut(self.provider))
        self.index_id = self.provider.index_id("NIFTY")
        self.slept: list[float] = []
        self.elapsed = 0.0
        self.held_at_push: list[int] | None = None  # the tokens held the moment the frames were pushed
        self.push_on_first_sleep = False
        self.wait = Wait(3.0, self._sleep, lambda: self.elapsed)

    def push_frames(self) -> None:
        self.held_at_push = self.provider.subscribed_tokens()
        for at, frame in self.frames:
            self.clock.now = at
            self.provider.on_frame(frame, at)

    async def _sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.elapsed += seconds
        if self.push_on_first_sleep and self.held_at_push is None:
            self.push_frames()

    def hold(self, ids) -> None:
        """Another consumer in the process holds ``ids`` and the feed has delivered everything."""
        self.feed.fanout.subscribe(lambda _q: None, list(ids))
        self.push_frames()


@pytest.fixture
def rig(monkeypatch):
    r = Rig()
    stub = {LEG_CONTRACT: SimpleNamespace(contract_id=LEG_CONTRACT, feed_key=LEG_ID)}

    async def resolve(_db, ids):
        return [stub[i] for i in ids]

    monkeypatch.setattr(tracked_contracts, "resolve", resolve)
    r.stub = stub
    return r


def _exit(direction: str, level: str) -> paper_trigger_store.NewTrigger:
    return paper_trigger_store.NewTrigger("conditional_exit", direction, D(level), underlying="NIFTY")  # type: ignore[arg-type]


def _leg(direction: str, level: str) -> paper_trigger_store.NewTrigger:
    return paper_trigger_store.NewTrigger("leg_stop", direction, D(level), contract_id=LEG_CONTRACT)  # type: ignore[arg-type]


def _now():
    raise AssertionError("a market context supplies its own clock")


async def _check(rig: Rig, new, *, ctx="rig", feed="rig"):
    return await paper_routes.check_trigger_levels(
        None, rig.ctx if ctx == "rig" else ctx, rig.feed if feed == "rig" else feed, "NIFTY", new, _now, rig.wait)


# ---- the core: nothing else holds the index ------------------------------------------------------------------------
async def test_core_an_unheld_index_above_x_is_refused_when_the_index_is_already_above_it(rig):
    rig.push_on_first_sleep = True  # the feed's frames arrive only after the read has asked for the index
    assert rig.provider.subscribed_tokens() == []
    assert await _check(rig, [_exit("above", "22500")]) == CROSSED
    assert rig.held_at_push, "the frames were pushed while the read held something"
    assert rig.held_at_push == [rig.provider._token_of[rig.index_id]]  # exactly the index, nothing else
    assert rig.provider.subscribed_tokens() == []  # the hold is released
    assert rig.provider.counters["unwanted_tick"] > 0  # the legs' ticks WERE dropped: only the held token booked


async def test_an_unheld_index_with_a_level_the_price_has_not_reached_is_allowed_in_market_hours(rig):
    rig.push_on_first_sleep = True
    assert await _check(rig, [_exit("above", "22600"), _exit("below", "22400")]) is None
    assert rig.provider.subscribed_tokens() == []


async def test_an_unheld_index_below_x_with_the_index_at_or_below_it_is_refused(rig):
    rig.push_on_first_sleep = True
    assert await _check(rig, [_exit("below", str(SPOT))]) == CROSSED  # at the level counts (stops.crossed)


async def test_a_held_index_above_x_is_refused_with_the_same_code_and_asks_for_nothing_more(rig):
    rig.hold([rig.index_id])
    assert await _check(rig, [_exit("above", "22500")]) == CROSSED
    assert rig.slept == []  # a live price was already there: no wait


# ---- ADR-327: market open and the price cannot be read ----------------------------------------------------------
async def test_market_open_and_no_price_after_the_wait_is_refused_with_the_adr_327_code(rig):
    assert await _check(rig, [_exit("above", "22600")]) == UNREADABLE  # no frame ever arrives
    assert WAIT_S <= rig.elapsed < WAIT_S + 2 * POLL_SECONDS  # it waited the 3 s (injected clock), then gave up
    assert rig.provider.subscribed_tokens() == []


def test_the_adr_327_refusal_line_is_verbatim():
    assert "Not saved: " + render(UNREADABLE).what_happened == VERBATIM


async def test_market_open_and_no_feed_context_is_refused(rig):
    at = rig.frames[0][0]
    assert await paper_routes.check_trigger_levels(None, None, None, "NIFTY", [_exit("above", "22600")],
                                                   lambda: at, rig.wait) == UNREADABLE


async def test_market_closed_with_no_feed_context_is_saved(rig):
    saturday = rig.frames[0][0].replace(day=10)  # 10 Oct 2026 is a Saturday
    assert await paper_routes.check_trigger_levels(None, None, None, "NIFTY", [_exit("above", "22600")],
                                                   lambda: saturday, rig.wait) is None


async def test_market_open_and_the_read_raises_is_refused(rig, monkeypatch):
    from ofo_app import market_read  # noqa: PLC0415

    def boom(*_a, **_k):
        raise RuntimeError("feed down")

    monkeypatch.setattr(market_read, "read_snapshot", boom)
    assert await _check(rig, [_exit("above", "22500")]) == UNREADABLE


async def test_market_open_with_a_context_but_no_fanout_reads_once_and_refuses_what_it_cannot_see(rig):
    assert await _check(rig, [_exit("above", "22600")], feed=None) == UNREADABLE
    assert rig.slept == []  # nothing to hold, so nothing to wait for


async def test_market_closed_is_saved_without_a_read_or_a_wait(rig):
    rig.clock.now = rig.frames[0][0].replace(day=10, hour=11)  # Saturday
    assert await _check(rig, [_exit("above", "22500")]) is None
    assert rig.slept == [] and rig.provider.subscribed_tokens() == []


# ---- leg stops ------------------------------------------------------------------------------------------------------
async def test_an_unheld_leg_stop_already_crossed_is_refused_as_a_leg_stop(rig):
    rig.push_on_first_sleep = True
    assert await _check(rig, [_leg("below", "500.00")]) == LEG_CROSSED  # the leg trades below 500
    assert rig.held_at_push == [rig.provider._token_of[LEG_ID]]


async def test_a_leg_stop_the_price_has_not_reached_is_allowed(rig):
    rig.push_on_first_sleep = True
    assert await _check(rig, [_leg("above", "5000.00")]) is None


async def test_a_leg_with_no_feed_key_in_market_hours_is_refused(rig):
    rig.stub[LEG_CONTRACT] = SimpleNamespace(contract_id=LEG_CONTRACT, feed_key=None)
    assert await _check(rig, [_leg("above", "5000.00")]) == UNREADABLE
    assert rig.slept == []


async def test_a_leg_with_no_feed_key_when_closed_is_saved(rig):
    rig.stub[LEG_CONTRACT] = SimpleNamespace(contract_id=LEG_CONTRACT, feed_key=None)
    rig.clock.now = rig.frames[0][0].replace(day=10, hour=11)
    assert await _check(rig, [_leg("above", "5000.00")]) is None


async def test_a_stale_price_after_the_wait_is_not_a_price(rig):
    rig.hold([rig.index_id])
    rig.clock.now = rig.clock.now.replace(minute=45)  # 25 min after the last tick, still inside market hours: stale
    assert await _check(rig, [_exit("above", "22600")]) == UNREADABLE


async def test_adr_330_39_an_old_index_quote_on_a_live_feed_is_unreadable_but_an_option_leg_is_not(rig):
    """D-69: the feed is live (a heartbeat 1 s ago; option contracts stay available however quiet, F-32) but the
    index's last tick is 61 s old: a conditional exit is refused with the ADR-327 (2) text and nothing is armed; a leg
    stop on the option contract is judged as before."""
    rig.hold([rig.index_id, LEG_ID])
    last = rig.clock.now
    rig.clock.now = last + datetime.timedelta(seconds=61)
    rig.provider.on_frame(b"\x00", rig.clock.now)  # a heartbeat: the whole feed is live
    assert rig.provider.status().health.value == "available"
    assert await _check(rig, [_exit("above", "22600")]) == UNREADABLE
    assert "Not saved: " + render(UNREADABLE).what_happened == VERBATIM
    assert await _check(rig, [_leg("above", "5000.00")]) is None


async def test_adr_330_39_an_index_quote_59_seconds_old_is_still_read(rig):
    rig.hold([rig.index_id, LEG_ID])
    rig.clock.now = rig.clock.now + datetime.timedelta(seconds=59)
    rig.provider.on_frame(b"\x00", rig.clock.now)
    assert await _check(rig, [_exit("above", "22600")]) is None


def test_every_recorded_contract_the_rig_uses_exists():
    _, _, items = new_provider()
    assert LEG_ID in all_instrument_ids(items)


# ---- the door itself: one state per price ---------------------------------------------------------------------------
async def _read(rig: Rig, **kw):
    from ofo_app.market_read import read_market  # noqa: PLC0415
    return await read_market(rig.ctx, rig.feed, "NIFTY", [LEG_ID], True, "trigger_check", wait=rig.wait, **kw)


async def test_read_market_gives_live_prices_with_the_recorded_values(rig):
    rig.hold([rig.index_id, LEG_ID])
    got = await _read(rig)
    assert (got.market_closed, got.index.state, got.index.price) == (False, "live", SPOT)
    assert got.legs[LEG_ID].state == "live" and got.legs[LEG_ID].price > 0


async def test_read_market_gives_missing_for_what_the_feed_never_delivers(rig):
    got = await _read(rig)
    assert (got.index.state, got.index.price, got.legs[LEG_ID].state, got.legs[LEG_ID].price) == (
        "missing", None, "missing", None)


async def test_read_market_gives_stale_when_the_last_tick_is_old(rig):
    rig.hold([rig.index_id, LEG_ID])
    rig.clock.now = rig.clock.now.replace(minute=45)
    got = await _read(rig)
    assert (got.index.state, got.index.price, got.legs[LEG_ID].state) == ("stale", None, "stale")


async def test_read_market_gives_market_closed_for_every_price_and_reads_nothing(rig):
    rig.clock.now = rig.frames[0][0].replace(day=10, hour=11)
    got = await _read(rig)
    assert got.market_closed and (got.index.state, got.legs[LEG_ID].state) == ("market_closed", "market_closed")
    assert rig.slept == [] and rig.provider.subscribed_tokens() == []


def test_the_production_wait_is_three_seconds_on_the_loops_own_sleep_and_clock():
    import asyncio  # noqa: PLC0415

    from ofo_app.market_read import DEFAULT_WAIT  # noqa: PLC0415

    assert (DEFAULT_WAIT.seconds, DEFAULT_WAIT.now, DEFAULT_WAIT.sleep) == (3.0, None, asyncio.sleep)
