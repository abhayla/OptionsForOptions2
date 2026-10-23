"""Gate 4a D-2 (ADR-075, ADR-020): the planned-entry (leg picker) route prices a contract that no live socket holds by
holding it on the shared fan-out until its first live quote arrives (bounded wait), then releasing exactly that hold.

Spec basis (quoted): ADR-075 "Save Draft stores each leg's planned entry price and its capture time with the strategy
definition"; ADR-020 Q185 "no fake prices": without a live price the answer is ``planned_entry: null`` with a reason
code, never a default, last-known or zero price.

Quote states the route can meet (brief B4 (d)), one test each:
  held and live            -> priced, not re-acquired, the other holder keeps its hold
  held by another, no quote yet -> route acquires its own hold, prices on the first tick, releases only its own
  unheld, a tick arrives   -> priced, released
  unheld, no tick in time  -> no_live_price (the existing code), nothing left subscribed
  unheld, a zero tick      -> no_live_price (zero is not a price), nothing left subscribed
  provider disconnected    -> not_connected, nothing subscribed
  client disconnect (task cancelled mid-wait) -> nothing left subscribed
Concurrent requests for one contract: one vendor subscription, both priced, none left.
Real rows: the recorded 2026-10-08 NIFTY instruments (tests/fixtures/kite_ws). No database, no Kite connection."""
from __future__ import annotations

import asyncio
import datetime
import pathlib
import sys
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay  # noqa: E402
from ofo.marketdata.fanout import FanOut  # noqa: E402
from ofo.marketdata.shared_compute import SharedCompute  # noqa: E402
import ofo.outcome.snapshot as snapshot_module  # noqa: E402
from ofo_app.live_push import LiveFeed  # noqa: E402
from ofo_app.main import create_app  # noqa: E402
from ofo_app.routes import planned_entry as route  # noqa: E402
from ofo_app.routes import outcome as outcome_route  # noqa: E402
from ofo_app.routes.outcome import MarketContext, OutcomeRequest, get_answer_clock, get_market_context  # noqa: E402

HTTP_OK = 200
RATE = Decimal("0.065")
LEGS = ["NSE_FO:44624", "NSE_FO:44632", "NSE_FO:44604", "NSE_FO:44595"]
ANSWER = datetime.datetime(2026, 10, 8, 3, 50, 5, tzinfo=datetime.UTC)
FEEDS = 2  # two users' feeds in the sharing test


def _frame(provider, instrument_id: str, rupees: str) -> bytes:
    token = provider._token_of[instrument_id]
    paise = int(Decimal(rupees) * 100)
    return (1).to_bytes(2, "big") + (8).to_bytes(2, "big") + token.to_bytes(4, "big") + paise.to_bytes(4, "big")


class Rig:
    """A connected provider with an EMPTY book. ``ticks`` maps an instrument to the price its first live tick carries;
    the tick lands ``delay`` seconds after the vendor subscription is taken (the socket answering Kite's subscribe)."""

    def __init__(self, connected: bool = True, *, book: bool = False, owner: str | None = None) -> None:
        self.provider, self.clock, items = new_provider()
        if book:  # the whole recorded 2026-10-08 book, every contract live (REQ-050: a snapshot to share)
            self.provider.subscribe(all_instrument_ids(items))
            replay(self.provider, self.clock)
        elif connected:
            self.provider.on_connected(self.clock.now)
        self.fanout = FanOut(self.provider)
        self.ctx = MarketContext(self.provider, lambda: self.clock.now, RATE, owner)
        self.feed = LiveFeed(self.ctx, self.fanout)
        self.ticks: dict[str, str] = {}
        self.delay = 0.1
        real = self.provider.subscribe

        def subscribe(ids):
            real(ids)
            for i in ids:
                if i in self.ticks:
                    asyncio.get_running_loop().call_later(
                        self.delay, lambda i=i: self.provider.on_frame(_frame(self.provider, i, self.ticks[i]),
                                                                        self.clock.now))
        self.provider.subscribe = subscribe

    def held(self, ids) -> list[str]:
        return [i for i in ids if self.fanout.subscriber_count(i) > 0]

    def wanted(self, ids) -> list[str]:
        return [i for i in ids if self.provider._token_of[i] in self.provider.subscribed_tokens()]

    def app(self):
        app = create_app()
        app.dependency_overrides[get_market_context] = lambda: self.ctx
        app.dependency_overrides[route.get_live_feed] = lambda: self.feed
        app.dependency_overrides[get_answer_clock] = lambda: (lambda: ANSWER)
        return app

    async def post(self, ids=LEGS):
        async with AsyncClient(transport=ASGITransport(app=self.app()), base_url="http://t") as ac:
            resp = await ac.post("/api/strategies/planned-entry", json={"underlying": "NIFTY", "instrument_ids": ids})
        assert resp.status_code == HTTP_OK, resp.text
        return resp.json()["entries"]


@pytest.fixture
def fast_wait(monkeypatch):
    monkeypatch.setattr(route, "PLANNED_ENTRY_WAIT_S", 0.4)


async def test_unheld_contracts_are_held_priced_then_released(fast_wait):
    rig = Rig()
    rig.ticks = dict(zip(LEGS, ["44.90", "11.75", "79.05", "37.15"], strict=True))
    entries = await rig.post()
    assert [e["planned_entry"] for e in entries] == ["44.90", "11.75", "79.05", "37.15"]
    assert all(e["source"] == "ltp" and e["reason_code"] is None for e in entries)
    assert rig.provider.counters["vendor_subscribe"] == len(LEGS)  # each leg was taken once from the vendor
    assert rig.held(LEGS) == [] and rig.wanted(LEGS) == []  # and nothing is left held


async def test_a_contract_held_and_live_by_another_is_priced_and_stays_held(fast_wait):
    rig = Rig()
    rig.ticks = {LEGS[0]: "44.90"}
    other = rig.fanout.subscribe(lambda q: None, [LEGS[0]])  # a strategy socket's hold
    await asyncio.sleep(0.2)  # its first tick lands
    before = rig.provider.counters["vendor_subscribe"]
    entries = await rig.post([LEGS[0]])
    assert entries[0]["planned_entry"] == "44.90"
    assert rig.provider.counters["vendor_subscribe"] == before  # not re-acquired
    assert rig.fanout.subscriber_count(LEGS[0]) == 1 and LEGS[0] in rig.wanted(LEGS)  # still the other holder's
    rig.fanout.unsubscribe(other)


async def test_a_contract_held_by_another_with_no_quote_yet_releases_only_its_own_hold(fast_wait):
    rig = Rig()
    other = rig.fanout.subscribe(lambda q: None, [LEGS[0]])  # held, but Kite has not sent a tick yet
    rig.ticks = {LEGS[0]: "44.90"}
    asyncio.get_running_loop().call_later(0.1, lambda: rig.provider.on_frame(
        _frame(rig.provider, LEGS[0], "44.90"), rig.clock.now))
    entries = await rig.post([LEGS[0]])
    assert entries[0]["planned_entry"] == "44.90"
    assert rig.fanout.subscriber_count(LEGS[0]) == 1 and rig.wanted(LEGS) == [LEGS[0]]  # the other hold survived
    rig.fanout.unsubscribe(other)
    assert rig.wanted(LEGS) == []


async def test_no_tick_in_time_gives_no_live_price_and_nothing_stays_subscribed(fast_wait):
    rig = Rig()  # no ticks: the vendor never answers
    entries = await rig.post(LEGS[:2])
    assert all(e["planned_entry"] is None and e["reason_code"] == "no_live_price" for e in entries)
    assert rig.held(LEGS) == [] and rig.wanted(LEGS) == []


async def test_a_zero_first_tick_is_not_a_price_and_is_released(fast_wait):
    rig = Rig()
    rig.ticks = {LEGS[0]: "0.00"}
    entries = await rig.post([LEGS[0]])
    assert entries[0]["planned_entry"] is None and entries[0]["reason_code"] == "no_live_price"
    assert rig.held(LEGS) == [] and rig.wanted(LEGS) == []


async def test_a_disconnected_provider_is_not_connected_and_subscribes_nothing(fast_wait):
    rig = Rig(connected=False)
    rig.ticks = {LEGS[0]: "44.90"}
    entries = await rig.post([LEGS[0]])
    assert entries[0]["reason_code"] == "not_connected" and entries[0]["planned_entry"] is None
    assert rig.provider.counters["vendor_subscribe"] == 0 and rig.held(LEGS) == []


async def test_a_client_that_goes_away_mid_wait_leaves_nothing_held(monkeypatch):
    monkeypatch.setattr(route, "PLANNED_ENTRY_WAIT_S", 5.0)
    rig = Rig()  # never ticks
    task = asyncio.ensure_future(rig.post([LEGS[0]]))
    await asyncio.sleep(0.3)
    assert rig.held(LEGS) == [LEGS[0]]  # held while waiting
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.05)
    assert rig.held(LEGS) == [] and rig.wanted(LEGS) == []


async def test_concurrent_requests_for_one_contract_share_one_vendor_subscription(fast_wait):
    rig = Rig()
    rig.ticks = {LEGS[0]: "44.90"}
    first, second = await asyncio.gather(rig.post([LEGS[0]]), rig.post([LEGS[0]]))
    assert first[0]["planned_entry"] == second[0]["planned_entry"] == "44.90"
    assert rig.provider.counters["vendor_subscribe"] == 1
    assert rig.held(LEGS) == [] and rig.wanted(LEGS) == []


async def test_req050_planned_entry_shares_the_forward_with_the_outcome_route_on_one_snapshot(monkeypatch):
    """REQ-050 AC-1/AC-3: two planned-entry requests and one outcome answer on one recorded snapshot of one feed run
    each expiry's forward once; another user's feed computes its own (ADR-053). Removing the route's FeedScope makes
    the second request compute again, so this goes red without it."""
    cache = SharedCompute()
    monkeypatch.setattr(outcome_route, "SHARED_COMPUTE", cache)
    calls: dict = {}
    real = snapshot_module.parity_forward

    def counted(chain, spot, expiry, valuation, rate):
        calls[expiry] = calls.get(expiry, 0) + 1
        return real(chain, spot, expiry, valuation, rate)

    monkeypatch.setattr(snapshot_module, "parity_forward", counted)
    rig = Rig(book=True, owner="user-1")
    await rig.post()
    assert calls and set(calls.values()) == {1}
    await rig.post()
    assert set(calls.values()) == {1} and cache.computations == len(calls)  # the second request computed nothing
    req = OutcomeRequest(underlying="NIFTY", legs=[{"instrument_id": i, "action": "SELL", "lots": 1,
                                                    "planned_entry": "10.00", "captured_at": ANSWER} for i in LEGS])
    outcome_route.outcome_response(req, rig.ctx)  # the real outcome path, same feed, same snapshot
    assert set(calls.values()) == {1}  # the outcome route read the planned-entry route's forward
    other = Rig(book=True, owner="user-2")
    await other.post()
    assert all(v == FEEDS for v in calls.values())  # another feed computes its own
