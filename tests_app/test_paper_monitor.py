"""GC-TP step 7a (REQ-109 AC-8; ADR-207 (5); ADR-015; ADR-119): the paper stop-loss monitor.

Spec basis (quoted): REQ-109 AC-8 "fires each trigger once (also across a restart)"; ADR-015 (stale is never live);
the brief's threat model: a trigger firing twice (two ticks, two monitors, a restart), a fire on a stale or missing
price, a fire outside market hours, a stop order larger than the open quantity.

Core proof (test_core_...): a FAKE quote stream through the REAL fan-out (ofo.marketdata.fanout.FanOut) and the REAL
database: ticks above the level fire nothing, one tick at level - 0.05 records exactly one stop order per open contract
at that tick's LTPs, sets fired_at and writes one alert; three more crossing ticks and a restarted monitor fire nothing.
The leg prices of a conditional exit come from the test's provider through the ``leg_prices`` seam (production:
read_snapshot + paper.leg_price, the routes' rule). Every test rolls back.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from ofo.marketdata.fanout import FanOut
from ofo.rules.inputs import DataHealth
from ofo.tracking import paper, stops
from ofo_app import paper_monitor, paper_store, tracked_contracts
from ofo_app import paper_trigger_store as triggers
from ofo_app.live_push import LiveFeed
from ofo_app.routes.outcome import MarketContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from test_index_live import FakeProvider, quote
from test_strategy_store import _user, _with_draft

D = Decimal
INDEX = "NSE_INDEX:1001"
OPEN_AT = datetime.datetime(2026, 10, 29, 4, 30, tzinfo=datetime.UTC)  # Thursday 10:00 IST, a trading day
AFTER_CLOSE = datetime.datetime(2026, 10, 29, 10, 31, tzinfo=datetime.UTC)  # 16:01 IST
LEVEL = D("22850.00")
OPEN_LEGS = 2  # the test strategy's open contracts


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


class Market:
    def __init__(self, at: datetime.datetime = OPEN_AT) -> None:
        self.at = at
        self.provider = FakeProvider({"NIFTY": INDEX})
        self.feed = LiveFeed(MarketContext(self.provider, lambda: self.at, D("0.065"), None), FanOut(self.provider))

    def tick(self, key: str, ltp: str, health: DataHealth = DataHealth.AVAILABLE) -> None:
        self.provider.tick(quote(key, "NIFTY", ltp, self.at, health))

    def leg_prices(self, _feed, _underlying, keys):
        return {k: paper.price_of(self.provider.quotes.get(k), k) for k in keys}


def _monitor(db, market: Market, **kwargs) -> paper_monitor.PaperMonitor:
    sessions = async_sessionmaker(bind=db, class_=AsyncSession, expire_on_commit=False,
                                  join_transaction_mode="create_savepoint")
    return paper_monitor.PaperMonitor(sessions, lambda: market.feed, leg_prices=market.leg_prices,
                                      monotonic=lambda: 0.0, **kwargs)


async def _strategy(db, lots: int = 1):
    """A NIFTY strategy: SELL lots x 65 of contract 0, BUY lots x 65 of contract 1 (open orders)."""
    user = _user()
    _, stored = await _with_draft(db, user)
    ids = stored.saved.contract_ids[:2]
    await paper_store.place(db, user, stored.id, [
        paper_store.NewOrder(ids[0], "SELL", 65 * lots, D("39.15"), "open", OPEN_AT),
        paper_store.NewOrder(ids[1], "BUY", 65 * lots, D("12.95"), "open", OPEN_AT)])
    keys = [c.feed_key for c in await tracked_contracts.resolve(db, ids)]
    return stored, ids, keys


async def _exit_below(db, sid: int, level: D = LEVEL) -> int:
    return await triggers.add(db, sid, triggers.NewTrigger("conditional_exit", "below", level, underlying="NIFTY"))


async def _stops(db, sid: int) -> list[tuple]:
    rows = await db.execute(text("SELECT contract_id, side, quantity, price, reason, trigger_id "
                                 "FROM public.paper_orders WHERE strategy_id = :s AND kind = 'stop' ORDER BY id"),
                            {"s": sid})
    return [tuple(r) for r in rows]


async def _trigger_state(db, tid: int) -> tuple[bool, bool]:
    r = (await db.execute(text("SELECT fired_at IS NOT NULL, cancelled_at IS NOT NULL FROM public.paper_triggers "
                               "WHERE id = :i"), {"i": tid})).one()
    return bool(r[0]), bool(r[1])


async def _alerts(db, sid: int) -> list[tuple]:
    rows = await db.execute(text("SELECT title, body FROM public.paper_alerts WHERE strategy_id = :s"), {"s": sid})
    return [tuple(r) for r in rows]


async def test_core_a_crossing_tick_fires_once_through_the_fan_out_and_never_again_after_a_restart(db):
    market = Market()
    stored, ids, keys = await _strategy(db)
    tid = await _exit_below(db, stored.id)
    monitor = _monitor(db, market)
    assert await monitor.step() == 0  # loads and subscribes the index and both open contracts
    assert {market.provider.vendor_subscribed >= {INDEX, *keys}} == {True}
    market.tick(keys[0], "41.00")
    market.tick(keys[1], "12.50")
    for level in ("22900.00", "22850.05"):
        market.tick(INDEX, level)
        assert await monitor.step() == 0
    market.tick(INDEX, "22849.95")
    assert await monitor.step() == 1
    reason = "Conditional exit: NIFTY crossed below 22,850.00"
    assert await _stops(db, stored.id) == [(ids[0], "BUY", 65, D("41.00"), reason, tid),
                                           (ids[1], "SELL", 65, D("12.50"), reason, tid)]
    assert await _trigger_state(db, tid) == (True, False)
    [(title, body)] = await _alerts(db, stored.id)
    assert title.startswith("Paper strategy - ") and body.startswith("Paper strategy - ")
    assert reason in body and "exited 2 legs at" in body and "41.00" in body and "no order was sent to Zerodha" in body
    for level in ("22849.90", "22800.00", "22700.00"):
        market.tick(INDEX, level)
        assert await monitor.step() == 0
    restarted = _monitor(db, market)
    assert await restarted.step() == 0
    market.tick(INDEX, "22600.00")
    assert await restarted.step() == 0
    assert len(await _stops(db, stored.id)) == OPEN_LEGS and len(await _alerts(db, stored.id)) == 1
    assert restarted.watched() == {}


async def test_two_monitors_seeing_the_same_tick_fire_once(db):
    market = Market()
    stored, _, keys = await _strategy(db)
    await _exit_below(db, stored.id)
    first, second = _monitor(db, market), _monitor(db, market)
    await first.step()
    await second.step()
    market.tick(keys[0], "41.00")
    market.tick(keys[1], "12.50")
    market.tick(INDEX, "22800.00")
    assert await first.step() + await second.step() == 1
    assert first.failures + second.failures == 0  # the loser finds no armed row; it never reaches the DB guard
    assert len(await _stops(db, stored.id)) == OPEN_LEGS


@pytest.mark.parametrize("health", [DataHealth.STALE, DataHealth.DELAYED, DataHealth.UNHEALTHY,
                                    DataHealth.UNAVAILABLE])
async def test_an_index_price_that_is_not_available_never_fires(db, health):
    market = Market()
    stored, _, keys = await _strategy(db)
    tid = await _exit_below(db, stored.id)
    monitor = _monitor(db, market)
    await monitor.step()
    market.tick(keys[0], "41.00")
    market.tick(keys[1], "12.50")
    market.tick(INDEX, "22800.00", health)
    assert await monitor.step() == 0
    market.tick(INDEX, "0")  # no trade yet: not a price
    assert await monitor.step() == 0
    assert await _trigger_state(db, tid) == (False, False) and await _stops(db, stored.id) == []


async def test_a_leg_without_a_live_price_holds_the_fire_and_the_trigger_stays_armed(db):
    market = Market()
    stored, _, keys = await _strategy(db)
    tid = await _exit_below(db, stored.id)
    monitor = _monitor(db, market)
    await monitor.step()
    market.tick(keys[0], "41.00")  # leg 1 missing
    market.tick(INDEX, "22800.00")
    assert await monitor.step() == 0
    market.tick(keys[1], "12.50", DataHealth.STALE)  # leg 1 stale
    market.tick(INDEX, "22800.00")
    assert await monitor.step() == 0
    assert await _trigger_state(db, tid) == (False, False)
    market.tick(keys[1], "12.50")
    market.tick(INDEX, "22795.00")
    assert await monitor.step() == 1


@pytest.mark.parametrize(("at", "holidays"), [
    (AFTER_CLOSE, None), (OPEN_AT, {2026: frozenset({datetime.date(2026, 10, 29)})}),
    (datetime.datetime(2026, 10, 31, 4, 30, tzinfo=datetime.UTC), None)], ids=["after-hours", "holiday", "weekend"])
async def test_nothing_fires_while_the_market_is_closed(db, at, holidays):
    market = Market(at)
    stored, _, keys = await _strategy(db)
    tid = await _exit_below(db, stored.id)
    monitor = _monitor(db, market, holidays=holidays)
    await monitor.step()
    market.tick(keys[0], "41.00")
    market.tick(keys[1], "12.50")
    market.tick(INDEX, "22800.00")
    assert await monitor.step() == 0
    assert await _trigger_state(db, tid) == (False, False)


async def test_a_leg_stop_exits_only_its_contract_for_its_whole_open_quantity_at_the_ticks_price(db):
    market = Market()
    stored, ids, keys = await _strategy(db, lots=2)
    tid = await triggers.add(db, stored.id, triggers.NewTrigger("leg_stop", "above", D("120.00"), contract_id=ids[0]))
    monitor = _monitor(db, market)
    await monitor.step()
    market.tick(keys[0], "119.95")
    assert await monitor.step() == 0
    market.tick(keys[0], "120.40")
    assert await monitor.step() == 1
    [(cid, side, qty, price, reason, trigger)] = await _stops(db, stored.id)
    assert (cid, side, qty, price, trigger) == (ids[0], "BUY", 130, D("120.40"), tid)
    assert reason.startswith("Stop-loss: ") and reason.endswith("crossed above 120.00")


async def test_a_fully_exited_strategy_cancels_its_triggers_and_places_nothing(db):
    market = Market()
    stored, ids, _ = await _strategy(db)
    tid = await _exit_below(db, stored.id)
    await paper_store.place(db, stored.user_ref, stored.id, [
        paper_store.NewOrder(ids[0], "BUY", 65, D("40.00"), "exit", OPEN_AT),
        paper_store.NewOrder(ids[1], "SELL", 65, D("12.00"), "exit", OPEN_AT)])
    monitor = _monitor(db, market)
    await monitor.step()
    market.tick(INDEX, "22800.00")
    assert await monitor.step() == 0
    assert await _trigger_state(db, tid) == (False, True) and await _stops(db, stored.id) == []


async def test_a_cancelled_trigger_never_fires(db):
    market = Market()
    stored, _, keys = await _strategy(db)
    tid = await _exit_below(db, stored.id)
    assert await triggers.cancel(db, stored.id, tid) == [tid]
    monitor = _monitor(db, market)
    await monitor.step()
    market.tick(keys[0], "41.00")
    market.tick(keys[1], "12.50")
    market.tick(INDEX, "22800.00")
    assert await monitor.step() == 0 and await _stops(db, stored.id) == []


@pytest.mark.parametrize(("level", "shown"), [(D("22850"), "22,850.00"), (D("22976.80"), "22,976.80"),
                                              (D("22976.85"), "22,976.85")])
def test_the_reason_text_shows_a_level_grouped_with_two_decimals(level, shown):
    trigger = stops.Trigger(1, 1, "conditional_exit", "below", level, underlying="NIFTY")
    assert str(paper_monitor.PaperMonitor._reason(trigger, {})) == f"Conditional exit: NIFTY crossed below {shown}"


async def test_claiming_one_armed_trigger_twice_wins_once_and_the_second_claim_does_not_raise(db):
    stored, _, _ = await _strategy(db)
    tid = await _exit_below(db, stored.id)
    assert await triggers.claim_fire(db, tid) is True
    assert await triggers.claim_fire(db, tid) is False


async def test_a_failed_write_rolls_back_whole_and_the_next_crossing_tick_fires(db, monkeypatch):
    market = Market()
    stored, _, keys = await _strategy(db)
    tid = await _exit_below(db, stored.id)
    monitor = _monitor(db, market)
    await monitor.step()
    market.tick(keys[0], "41.00")
    market.tick(keys[1], "12.50")
    real_alert = triggers.add_alert

    async def broken(*_a, **_k):
        raise ConnectionError("database went away")

    monkeypatch.setattr(triggers, "add_alert", broken)  # fails AFTER the claim and the stop orders
    market.tick(INDEX, "22800.00")
    assert await monitor.step() == 0 and monitor.failures == 1
    assert await _trigger_state(db, tid) == (False, False) and await _stops(db, stored.id) == []
    monkeypatch.setattr(triggers, "add_alert", real_alert)
    market.tick(INDEX, "22790.00")
    assert await monitor.step() == 1 and len(await _stops(db, stored.id)) == OPEN_LEGS
