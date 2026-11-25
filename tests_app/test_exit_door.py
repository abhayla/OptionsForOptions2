"""Phase 4 (modular doors, ADR-328 (4); PLAN-phases-3-8 5.4): the exit door. Every server path that builds paper exit
orders (the tracking exit route, the manual orders route, the monitor's stops, the expiry settlement) stores exactly the
rows it stored before the door existed.

Core: "given a strategy, exit its open legs at market" is one server function. Proof: a real 4-leg NIFTY condor (the
strategy-155 legs of test_paper_batch_buys_first.py) is exited through each caller and the stored rows are compared with
GOLDEN lists captured from the code of the pre-phase head (491ca7e2) BEFORE anything moved. Rows are
(leg index, side, quantity, price, kind, reason, trigger, placed_at); a leg index is the position in the strategy's
saved contract ids (or the sorted ids for the monitor, which fires in id order); the trigger is "TID" when it is the
trigger the test armed. Real PostgreSQL; every test but the race test rolls back.
"""
from __future__ import annotations

import asyncio
import datetime
from decimal import Decimal
from http import HTTPStatus
from types import SimpleNamespace

import pytest
import test_paper_monitor as pm
import test_paper_settlement as ps_t
from httpx import ASGITransport, AsyncClient
from ofo.errors import render
from ofo.timeutil import IST
from ofo_app import paper_monitor, paper_store, settings_store, tracked_contracts
from ofo_app import paper_settlement as ps
from ofo_app import paper_trigger_store as triggers
from ofo_app.routes import tracking as tracking_routes
from ofo_app.routes.outcome import MarketContext, get_answer_clock, get_market_context
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from test_execution_plan_store import _remove_own_rows
from test_strategy_store import _app, _client, _user, _with_draft
from test_strategy_tracking import _DELIST, ANSWERED, _market, _open_book, _paper_body, _setup

D = Decimal
UTC = datetime.UTC
OK, CREATED, CONFLICT = HTTPStatus.OK, HTTPStatus.CREATED, HTTPStatus.CONFLICT
OPENS = 4  # the condor's four opening orders


def dt(*parts: int) -> datetime.datetime:
    return datetime.datetime(*parts, tzinfo=UTC)


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _closing(db, sid: int, ids: list[int], tid: int | None = None) -> list[tuple]:
    """The non-open rows in the order the Orderbook reads them (id): (leg index, side, quantity, price, kind, reason,
    trigger, placed_at). The trigger is "TID" when it is ``tid``."""
    rows = await db.execute(text("SELECT contract_id, side, quantity, price, kind, reason, trigger_id, placed_at "
                                 "FROM public.paper_orders WHERE strategy_id = :s AND kind <> 'open' ORDER BY id"),
                            {"s": sid})
    return [(ids.index(r[0]), r[1], r[2], r[3], r[4], r[5], "TID" if tid is not None and r[6] == tid else r[6], r[7])
            for r in rows]


# --- goldens, captured from 491ca7e2 (the pre-phase head) ----------------------------------------------------------

GOLDEN_TRACKING_ALL: list[tuple] = [
    (0, 'BUY', 65, D('39.15'), 'exit', None, None, dt(2026, 10, 8, 3, 50, 8)),
    (2, 'BUY', 65, D('82.75'), 'exit', None, None, dt(2026, 10, 8, 3, 50, 9)),
    (1, 'SELL', 65, D('12.95'), 'exit', None, None, dt(2026, 10, 8, 3, 50, 9)),
    (3, 'SELL', 65, D('35.80'), 'exit', None, None, dt(2026, 10, 8, 3, 50, 9)),
]
GOLDEN_TRACKING_ONE: list[tuple] = [
    (1, 'SELL', 65, D('12.95'), 'exit', None, None, dt(2026, 10, 8, 3, 50, 9)),
]
GOLDEN_MANUAL_ALL: list[tuple] = [
    (0, 'BUY', 65, D('39.15'), 'exit', None, None, dt(2026, 10, 8, 4, 0)),
    (2, 'BUY', 65, D('82.75'), 'exit', None, None, dt(2026, 10, 8, 4, 0)),
    (1, 'SELL', 65, D('12.95'), 'exit', None, None, dt(2026, 10, 8, 4, 0)),
    (3, 'SELL', 65, D('35.80'), 'exit', None, None, dt(2026, 10, 8, 4, 0)),
]
GOLDEN_MANUAL_PARTIAL: list[tuple] = [
    (0, 'BUY', 65, D('39.15'), 'exit', None, None, dt(2026, 10, 8, 4, 0)),
]
GOLDEN_CONDITIONAL: list[tuple] = [
    (0, 'BUY', 65, D('41.00'), 'stop',
     'Stop-loss on the index: NIFTY crossed below 22,850.00; NIFTY was at 22,849.95 at that moment',
     'TID', dt(2026, 10, 29, 4, 30)),
    (2, 'BUY', 65, D('30.25'), 'stop',
     'Stop-loss on the index: NIFTY crossed below 22,850.00; NIFTY was at 22,849.95 at that moment',
     'TID', dt(2026, 10, 29, 4, 30)),
    (1, 'SELL', 65, D('12.50'), 'stop',
     'Stop-loss on the index: NIFTY crossed below 22,850.00; NIFTY was at 22,849.95 at that moment',
     'TID', dt(2026, 10, 29, 4, 30)),
    (3, 'SELL', 65, D('8.75'), 'stop',
     'Stop-loss on the index: NIFTY crossed below 22,850.00; NIFTY was at 22,849.95 at that moment',
     'TID', dt(2026, 10, 29, 4, 30)),
]
GOLDEN_LEG_STOP: list[tuple] = [
    (0, 'BUY', 130, D('120.40'), 'stop',
     'Stop-loss: NIFTY 13 Oct 22800 CE crossed above 120.00; NIFTY was at 22,849.95 at that moment',
     'TID', dt(2026, 10, 29, 4, 30)),
]
GOLDEN_SETTLE: list[tuple] = [
    (0, 'BUY', 65, D('0.00'), 'settle',
     'Paper - settled at expiry: NIFTY closed at 22,900.00',
     None, dt(2026, 10, 13, 10, 0)),
    (2, 'BUY', 65, D('100.00'), 'settle',
     'Paper - settled at expiry: NIFTY closed at 22,900.00',
     None, dt(2026, 10, 13, 10, 0)),
    (1, 'SELL', 65, D('0.00'), 'settle',
     'Paper - settled at expiry: NIFTY closed at 22,900.00',
     None, dt(2026, 10, 13, 10, 0)),
    (3, 'SELL', 65, D('0.00'), 'settle',
     'Paper - settled at expiry: NIFTY closed at 22,900.00',
     None, dt(2026, 10, 13, 10, 0)),
]


async def test_tracking_exit_all_four_condor_legs_rows_match_golden(db):
    app, stored, *_ = await _setup(db)
    async with _client(app) as client:
        await _open_book(client, stored)
        reply = await client.post(f"/strategies/{stored.id}/tracking/exit", json={"legs": [0, 1, 2, 3]})
    assert reply.status_code == OK, reply.text
    assert await _closing(db, stored.id, list(stored.saved.contract_ids)) == GOLDEN_TRACKING_ALL


async def test_tracking_exit_one_named_leg_rows_match_golden(db):
    app, stored, *_ = await _setup(db)
    ids = list(stored.saved.contract_ids)
    async with _client(app) as client:
        await _open_book(client, stored)
        reply = await client.post(f"/strategies/{stored.id}/tracking/exit", json={"legs": [1]})
    assert reply.status_code == OK, reply.text
    rows = await _closing(db, stored.id, ids)
    assert [r[0] for r in rows] == [1]  # subset only; the other three legs are untouched
    assert rows == GOLDEN_TRACKING_ONE


def _exit_body(stored, quantities: dict[int, int]) -> dict:
    """The browser's exit orders: the browser's price (99.00) is sent and must be ignored."""
    legs = stored.saved.definition.legs
    return {"orders": [{"contract_id": stored.saved.contract_ids[i], "quantity": q, "kind": "exit", "price": "99.00",
                        "side": "BUY" if legs[i].action.value == "SELL" else "SELL"} for i, q in quantities.items()]}


async def test_manual_exit_all_rows_match_golden(db):
    app, stored, *_ = await _setup(db)
    async with _client(app) as client:
        await _open_book(client, stored)
        reply = await client.post(f"/paper/strategies/{stored.id}/orders",
                                  json=_exit_body(stored, {0: 65, 1: 65, 2: 65, 3: 65}))
    assert reply.status_code == CREATED, reply.text
    rows = await _closing(db, stored.id, list(stored.saved.contract_ids))
    assert all(r[3] != D("99.00") for r in rows)  # the server's live price, never the browser's
    assert rows == GOLDEN_MANUAL_ALL


async def test_manual_partial_exit_one_lot_rows_match_golden(db):
    app, stored, *_ = await _setup(db)
    opening = _paper_body(stored)
    opening["orders"][0]["quantity"] = 130  # two lots held on leg 0
    async with _client(app) as client:
        placed = await client.post(f"/paper/strategies/{stored.id}/orders", json=opening)
        assert placed.status_code == CREATED, placed.text
        reply = await client.post(f"/paper/strategies/{stored.id}/orders", json=_exit_body(stored, {0: 65}))
    assert reply.status_code == CREATED, reply.text
    rows = await _closing(db, stored.id, list(stored.saved.contract_ids))
    assert [(r[0], r[2]) for r in rows] == [(0, 65)]  # one lot stored, one lot still open
    assert rows == GOLDEN_MANUAL_PARTIAL


async def _condor_held(db):
    """Strategy 155's shape on the monitor's market: held SELL ids[0], BUY ids[1], SELL ids[2], BUY ids[3] (ids sorted:
    the monitor fires in contract-id order)."""
    user = _user()
    _, stored = await _with_draft(db, user)
    ids = sorted(stored.saved.contract_ids)
    await paper_store.place(db, user, stored.id, [
        paper_store.NewOrder(ids[0], "SELL", 65, D("10.00"), "open", pm.OPEN_AT),
        paper_store.NewOrder(ids[1], "BUY", 65, D("5.00"), "open", pm.OPEN_AT),
        paper_store.NewOrder(ids[2], "SELL", 65, D("8.00"), "open", pm.OPEN_AT),
        paper_store.NewOrder(ids[3], "BUY", 65, D("4.00"), "open", pm.OPEN_AT)])
    keys = [c.feed_key for c in await tracked_contracts.resolve(db, ids)]
    return stored, ids, keys


async def test_conditional_exit_rows_match_golden(db):
    market = pm.Market()
    stored, ids, keys = await _condor_held(db)
    tid = await pm._exit_below(db, stored.id)
    monitor = pm._monitor(db, market)
    assert await monitor.step() == 0
    for key, ltp in zip(keys, ["41.00", "12.50", "30.25", "8.75"], strict=True):
        market.tick(key, ltp)
    market.tick(pm.INDEX, "22849.95")
    assert await monitor.step() == 1
    assert await _closing(db, stored.id, ids, tid) == GOLDEN_CONDITIONAL


async def test_leg_stop_rows_match_golden(db):
    market = pm.Market()
    stored, ids, keys = await pm._strategy(db, lots=2)  # SELL 130 of ids[0], BUY 130 of ids[1]
    tid = await triggers.add(db, stored.id, triggers.NewTrigger("leg_stop", "above", D("120.00"), contract_id=ids[0]))
    monitor = pm._monitor(db, market)
    await monitor.step()
    market.tick(pm.INDEX, "22849.95")
    market.tick(keys[0], "120.40")
    assert await monitor.step() == 1
    rows = await _closing(db, stored.id, ids, tid)
    assert [(r[0], r[1], r[2]) for r in rows] == [(0, "BUY", 130)]  # one contract, its whole open quantity
    assert rows == GOLDEN_LEG_STOP


async def _two_expiry(db):
    """A NIFTY condor (expiry 13 Oct, four legs) plus one SENSEX leg (29 Oct): on 14 Oct only the condor is due."""
    user = _user()
    _, stored = await _with_draft(db, user)
    sensex = await ps_t._catalogue(db)
    ids = sorted(stored.saved.contract_ids)
    far = sensex[876359]
    await paper_store.place(db, user, stored.id, [
        paper_store.NewOrder(ids[0], "SELL", 65, D("10.00"), "open", ps_t.OPENED),
        paper_store.NewOrder(ids[1], "BUY", 65, D("5.00"), "open", ps_t.OPENED),
        paper_store.NewOrder(ids[2], "SELL", 65, D("8.00"), "open", ps_t.OPENED),
        paper_store.NewOrder(ids[3], "BUY", 65, D("4.00"), "open", ps_t.OPENED),
        paper_store.NewOrder(far, "BUY", 20, D("300.00"), "open", ps_t.OPENED)])
    return stored, ids, far


SETTLE_AT = datetime.datetime(2026, 10, 14, 10, 0, tzinfo=ps_t.IST)


async def _nifty_close(underlying, expiry):
    return D("22900.00") if (underlying, expiry) == ("NIFTY", datetime.date(2026, 10, 13)) else None


async def test_settlement_rows_match_golden(db):
    """A two-expiry trade: the NIFTY condor (expiry 13 Oct) is due on 14 Oct, one SENSEX leg (29 Oct) is not."""
    stored, ids, far = await _two_expiry(db)
    run = await ps.settle_expired(db, SETTLE_AT, _nifty_close)
    assert far not in [s.contract_id for s in run.settled if s.strategy_id == stored.id]  # only the due contracts
    rows = await _closing(db, stored.id, ids)
    assert rows == GOLDEN_SETTLE


# --- row 8: fail-closed rows (nothing stored, code unchanged) --------------------------------------------------------


def _code(template: str) -> str:
    return render(template).code


def _refused(reply, template: str, status: int = CONFLICT) -> None:
    assert (reply.status_code, reply.json().get("code")) == (status, _code(template)), reply.text


async def _exit_call(app, stored, caller: str, legs: list[int], *, raise_app: bool = True):
    transport = ASGITransport(app=app, raise_app_exceptions=raise_app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        if caller == "tracking":
            return await client.post(f"/strategies/{stored.id}/tracking/exit", json={"legs": legs})
        return await client.post(f"/paper/strategies/{stored.id}/orders",
                                 json=_exit_body(stored, dict.fromkeys(legs, 65)))


async def _opened(db):
    app, stored, provider, clock, last = await _setup(db)
    async with _client(app) as client:
        await _open_book(client, stored)
    return app, stored, provider, clock, last


def _context(app, provider, at):
    app.dependency_overrides[get_market_context] = lambda: MarketContext(provider, lambda: at, D("0.065"))


CALLERS = ["tracking", "orders"]


@pytest.mark.parametrize("caller", CALLERS)
async def test_no_market_context_is_refused_not_connected_and_nothing_is_stored(db, caller):
    app, stored, *_ = await _opened(db)
    app.dependency_overrides[get_market_context] = lambda: None
    reply = await _exit_call(app, stored, caller, [0, 1])
    _refused(reply, "tracking_not_connected")
    assert await _closing(db, stored.id, list(stored.saved.contract_ids)) == []


@pytest.mark.parametrize(("caller", "template"), [("tracking", "tracking_not_connected"),
                                                  ("orders", "tracking_exit_prices_not_live")])
async def test_a_disconnected_provider_is_refused_per_caller_and_nothing_is_stored(db, monkeypatch, caller, template):
    """L3 kept: the tracking route asks the provider's status first; the orders route only has "no context"."""
    app, stored, provider, clock, last = await _opened(db)
    monkeypatch.setattr(provider, "status", lambda: SimpleNamespace(connected=False))
    clock.now = last + datetime.timedelta(minutes=10)  # a lost connection: the quotes age out
    reply = await _exit_call(app, stored, caller, [0, 1])
    _refused(reply, template)
    assert await _closing(db, stored.id, list(stored.saved.contract_ids)) == []


@pytest.mark.parametrize("caller", CALLERS)
async def test_a_contract_not_live_is_refused_contract_not_live_and_nothing_is_stored(db, caller):
    app, stored, *_ = await _opened(db)
    await db.execute(text(_DELIST), {"id": stored.saved.contract_ids[0]})
    reply = await _exit_call(app, stored, caller, [0, 1])
    _refused(reply, "tracking_exit_contract_not_live")
    assert await _closing(db, stored.id, list(stored.saved.contract_ids)) == []


@pytest.mark.parametrize("caller", CALLERS)
async def test_a_stale_price_refuses_the_whole_exit_and_nothing_is_stored(db, caller):
    app, stored, _provider, clock, last = await _opened(db)
    clock.now = last + datetime.timedelta(minutes=10)  # every quote is ten minutes old
    reply = await _exit_call(app, stored, caller, [0, 1])
    _refused(reply, "tracking_exit_prices_not_live")
    assert await _closing(db, stored.id, list(stored.saved.contract_ids)) == []


@pytest.mark.parametrize(("caller", "status", "code"), [("orders", CONFLICT, "tracking_exit_prices_not_live"),
                                                         ("tracking", HTTPStatus.INTERNAL_SERVER_ERROR, None)])
async def test_a_price_read_that_raises_is_409_for_orders_and_500_for_tracking(db, monkeypatch, caller, status, code):
    """L2 kept: a failed read is "no price" on the orders route, an unhandled error on the tracking route."""
    app, stored, *_ = await _opened(db)

    async def broken(*_a, **_k):
        raise RuntimeError("the price read failed")
    monkeypatch.setattr(tracking_routes, "_snapshot", broken)
    reply = await _exit_call(app, stored, caller, [0, 1], raise_app=False)
    assert reply.status_code == status
    if code is not None:
        assert reply.json()["code"] == _code(code)
    assert await _closing(db, stored.id, list(stored.saved.contract_ids)) == []


@pytest.mark.parametrize("caller", CALLERS)
async def test_a_closed_market_is_refused_before_any_price_is_read(db, caller):
    app, stored, provider, *_ = await _opened(db)
    after = datetime.datetime(2026, 10, 8, 18, 0, tzinfo=IST)
    _context(app, provider, after)
    app.dependency_overrides[get_answer_clock] = lambda: lambda: after
    reply = await _exit_call(app, stored, caller, [0, 1])
    _refused(reply, "gate_market_closed")
    assert await _closing(db, stored.id, list(stored.saved.contract_ids)) == []


async def test_an_order_larger_than_the_open_quantity_is_refused_and_nothing_is_stored(db):
    app, stored, *_ = await _opened(db)
    body = _exit_body(stored, {0: 130})
    async with _client(app) as client:
        reply = await client.post(f"/paper/strategies/{stored.id}/orders", json=body)
    _refused(reply, "paper_exit_exceeds_open", HTTPStatus.UNPROCESSABLE_ENTITY)
    assert await _closing(db, stored.id, list(stored.saved.contract_ids)) == []


async def test_a_leg_already_exited_is_refused_and_only_the_first_exit_is_stored(db):
    app, stored, *_ = await _opened(db)
    first = await _exit_call(app, stored, "tracking", [2])
    assert first.status_code == OK, first.text
    again = await _exit_call(app, stored, "tracking", [2, 3])
    _refused(again, "tracking_leg_already_exited")
    assert [r[0] for r in await _closing(db, stored.id, list(stored.saved.contract_ids))] == [2]


# --- rows 9 and 10: the monitor, no price and nothing open -----------------------------------------------------------


async def test_monitor_missing_price_keeps_the_trigger_armed_and_stores_nothing(db):
    market = pm.Market()
    stored, ids, keys = await _condor_held(db)
    tid = await pm._exit_below(db, stored.id)
    monitor = pm._monitor(db, market)
    assert await monitor.step() == 0
    for key, ltp in zip(keys[:3], ["41.00", "12.50", "30.25"], strict=True):
        market.tick(key, ltp)  # the fourth leg never ticks: no live price for it
    market.tick(pm.INDEX, "22849.95")
    assert await monitor.step() == 0  # NotYet
    assert await pm._trigger_state(db, tid) == (False, False)  # still armed
    assert await _closing(db, stored.id, ids) == []
    assert monitor.failures == 0


async def test_flat_strategy_cancels_triggers_and_stores_nothing(db):
    market = pm.Market()
    stored, ids, _keys = await _condor_held(db)
    await paper_store.place(db, stored.user_ref, stored.id, [  # every leg exits by hand: the strategy is flat
        paper_store.NewOrder(ids[0], "BUY", 65, D("9.00"), "exit", pm.OPEN_AT),
        paper_store.NewOrder(ids[1], "SELL", 65, D("5.50"), "exit", pm.OPEN_AT),
        paper_store.NewOrder(ids[2], "BUY", 65, D("7.00"), "exit", pm.OPEN_AT),
        paper_store.NewOrder(ids[3], "SELL", 65, D("4.50"), "exit", pm.OPEN_AT)])
    flat_rows = await _closing(db, stored.id, ids)
    tid = await pm._exit_below(db, stored.id)  # armed on a flat strategy (a trigger saved just before the last exit)
    monitor = pm._monitor(db, market)
    assert await monitor.step() == 0
    market.tick(pm.INDEX, "22849.95")
    assert await monitor.step() == 0
    assert await pm._trigger_state(db, tid) == (False, True)  # cancelled, never fired
    assert await _closing(db, stored.id, ids) == flat_rows  # nothing new stored
    assert await pm._alerts(db, stored.id) == []


async def test_a_leg_stop_on_a_flat_leg_cancels_only_itself(db):
    market = pm.Market()
    stored, ids, keys = await pm._strategy(db)  # SELL ids[0], BUY ids[1]
    await paper_store.place(db, stored.user_ref, stored.id,
                            [paper_store.NewOrder(ids[0], "BUY", 65, D("9.00"), "exit", pm.OPEN_AT)])
    stop = await triggers.add(db, stored.id, triggers.NewTrigger("leg_stop", "above", D("120.00"), contract_id=ids[0]))
    other = await triggers.add(db, stored.id, triggers.NewTrigger("leg_stop", "below", D("5.00"), contract_id=ids[1]))
    monitor = pm._monitor(db, market)
    await monitor.step()
    market.tick(keys[0], "125.00")
    assert await monitor.step() == 0
    assert await pm._trigger_state(db, stop) == (False, True)
    assert await pm._trigger_state(db, other) == (False, False)  # the open leg's own stop stays armed
    assert await pm._stops(db, stored.id) == []


# --- row 12: a leg added between the book read and the lock ----------------------------------------------------------


async def _add_a_lot(db, stored, leg: int) -> None:
    """Another writer commits one more lot of leg ``leg`` (the same side it is held on)."""
    held = stored.saved.definition.legs[leg]
    await paper_store.place(db, stored.user_ref, stored.id, [paper_store.NewOrder(
        stored.saved.contract_ids[leg], held.action.value, 65, D("40.00"), "open", ANSWERED)])


GOLDEN_RACE_TRACKING: list[tuple] = [
    (0, "BUY", 65, D("39.15"), "exit", None, None, dt(2026, 10, 8, 3, 50, 8)),
]


async def test_a_leg_added_between_read_and_lock_tracking_route_part_closes_the_old_quantity(db, monkeypatch):
    """The tracking route keeps today's sides and quantities (5.4.3): it closes what its own book read showed (65), the
    lot added after the read stays open."""
    app, stored, *_ = await _opened(db)
    real = tracking_routes._snapshot

    async def racing(*args, **kwargs):
        await _add_a_lot(db, stored, 0)  # after the route's book read, before its write
        return await real(*args, **kwargs)
    monkeypatch.setattr(tracking_routes, "_snapshot", racing)
    reply = await _exit_call(app, stored, "tracking", [0])
    assert reply.status_code == OK, reply.text
    assert await _closing(db, stored.id, list(stored.saved.contract_ids)) == GOLDEN_RACE_TRACKING


class _After:
    """``paper_monitor``'s view of a module, with one async function run once (the race) before the real one."""

    def __init__(self, real, name: str, hook) -> None:
        self._real, self._name, self._hook, self._done = real, name, hook, False

    def __getattr__(self, name: str):
        attr = getattr(self._real, name)
        if name != self._name:
            return attr

        async def hooked(*args, **kwargs):
            if not self._done:
                self._done = True
                await self._hook()
            return await attr(*args, **kwargs)
        return hooked


async def test_a_leg_added_between_read_and_lock_the_monitor_closes_the_whole_locked_quantity(db, monkeypatch):
    """5.4.3, race-only: the monitor reads the net under the lock, so the lot added after its first look is closed too
    (today it stays open with no stop). The stop is 130, not 65."""
    market = pm.Market()
    stored, ids, keys = await pm._strategy(db)  # SELL 65 ids[0], BUY 65 ids[1]
    tid = await triggers.add(db, stored.id, triggers.NewTrigger("leg_stop", "above", D("120.00"), contract_id=ids[0]))
    monitor = pm._monitor(db, market)
    await monitor.step()  # loads the watch; the race starts at the fire

    async def add_a_lot() -> None:  # another writer commits after the monitor's first book read
        await paper_store.place(db, stored.user_ref, stored.id, [
            paper_store.NewOrder(ids[0], "SELL", 65, D("40.00"), "open", pm.OPEN_AT)])
    monkeypatch.setattr(paper_monitor, "tracked_contracts",
                        _After(tracked_contracts, "resolve", add_a_lot))  # resolve runs after the first read
    market.tick(pm.INDEX, "22849.95")
    market.tick(keys[0], "120.40")
    assert await monitor.step() == 1
    rows = await _closing(db, stored.id, ids, tid)
    assert [(r[0], r[1], r[2], r[3], r[4]) for r in rows] == [(0, "BUY", 130, D("120.40"), "stop")]


# --- row 13: a raise on the third insert stores nothing (A1, the half exit) ------------------------------------------


@pytest.fixture
def third_insert_fails(db):
    """The third ``INSERT INTO paper_orders`` of the test raises."""
    seen: list[int] = []
    armed = [False]

    def listener(_conn, _cursor, statement, *_rest):
        if armed[0] and statement.lstrip().startswith("INSERT INTO public.paper_orders"):
            seen.append(1)
            if len(seen) == 3:  # noqa: PLR2004
                raise RuntimeError("the third insert failed")
    seen_arm = SimpleNamespace(seen=seen, arm=lambda: armed.__setitem__(0, True))
    event.listen(db.sync_engine, "before_cursor_execute", listener)
    yield seen_arm
    event.remove(db.sync_engine, "before_cursor_execute", listener)


async def test_failed_insert_on_order_three_stores_nothing_tracking_route(db, third_insert_fails):
    app, stored, *_ = await _opened(db)
    third_insert_fails.arm()
    ids = list(stored.saved.contract_ids)
    reply = await _exit_call(app, stored, "tracking", [0, 1, 2, 3], raise_app=False)
    assert reply.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert len(third_insert_fails.seen) == 3  # noqa: PLR2004 - two inserts were made, then the third raised
    assert await _closing(db, stored.id, ids) == []  # all rolled back
    assert (await db.execute(text("SELECT status FROM public.strategies WHERE id = :i"),
                             {"i": stored.id})).scalar_one() == "draft"


async def test_failed_insert_on_order_three_stores_nothing_monitor(db, third_insert_fails):
    market = pm.Market()
    stored, ids, keys = await _condor_held(db)
    tid = await pm._exit_below(db, stored.id)
    monitor = pm._monitor(db, market)
    assert await monitor.step() == 0
    third_insert_fails.arm()
    for key, ltp in zip(keys, ["41.00", "12.50", "30.25", "8.75"], strict=True):
        market.tick(key, ltp)
    market.tick(pm.INDEX, "22849.95")
    assert await monitor.step() == 0
    assert monitor.failures == 1
    assert await _closing(db, stored.id, ids) == []
    assert await pm._trigger_state(db, tid) == (False, False)  # the claim rolled back with the rest: retried next tick


async def test_failed_insert_on_order_three_stores_nothing_settlement(db, third_insert_fails):
    stored, ids, _far = await _two_expiry(db)
    third_insert_fails.arm()
    run = await ps.settle_expired(db, SETTLE_AT, _nifty_close)
    assert run.failed == (stored.id,)
    assert await _closing(db, stored.id, ids) == []


# --- row 11: the monitor and the tracking exit at once ---------------------------------------------------------------


async def _remove_paper_rows(admin_engine, user_ref: str, contract_ids: list[int]) -> None:
    async with admin_engine.connect() as conn:  # noqa: SIM117
        async with conn.begin():
            mine = "(SELECT id FROM public.strategies WHERE user_ref = :u)"
            for table in ("paper_alerts", "paper_triggers", "paper_orders"):
                await conn.execute(text(f'ALTER TABLE public."{table}" DISABLE TRIGGER USER'))
                await conn.execute(text(f"DELETE FROM public.{table} WHERE strategy_id IN {mine}"),  # noqa: S608
                                   {"u": user_ref})
                await conn.execute(text(f'ALTER TABLE public."{table}" ENABLE TRIGGER USER'))
    await _remove_own_rows(admin_engine, contract_ids, user_ref)


async def _someone_waits_on_a_lock(engine) -> bool:
    async with engine.connect() as conn:
        return (await conn.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                                        "AND wait_event_type = 'Lock'"))).scalar_one() > 0


class _Pause:
    """``paper_monitor``'s view of a module whose one function stops (``reached`` set) until ``go`` is set."""

    def __init__(self, real, name: str, reached: asyncio.Event, go: asyncio.Event) -> None:
        self._real, self._name, self._reached, self._go = real, name, reached, go

    def __getattr__(self, name: str):
        attr = getattr(self._real, name)
        if name != self._name:
            return attr

        async def paused(*args, **kwargs):
            self._reached.set()
            await self._go.wait()
            return await attr(*args, **kwargs)
        return paused


@pytest.mark.parametrize("pause_at", ["before_claim", "before_place"])
async def test_monitor_and_tracking_exit_at_once_one_wins_no_deadlock(  # noqa: PLR0915 - one step-driven scenario
       app_engine, admin_engine, monkeypatch, pause_at):
    """Two real connections, driven step by step: the monitor stops at ``pause_at`` (its claim, or its write), the
    tracking exit of all four legs runs, then the monitor goes on. A3 (reasoned in the phase-4 report): the monitor's
    claim locks the trigger row and its write then waits for the strategy lock, while the route holds the strategy lock
    and its reconcile waits for that trigger row. Exactly one set of closing rows is stored (four exits OR four stops),
    the loser stores nothing and nobody is told "deadlock detected"."""
    user = _user()
    contract_ids: list[int] = []
    sessions = async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with app_engine.connect() as setup:
            before = {r[0] for r in await setup.execute(text("SELECT id FROM public.catalogue_contracts"))}
            await setup.rollback()
            async with setup.begin():
                _, stored = await _with_draft(setup, user)
                after = {r[0] for r in await setup.execute(text("SELECT id FROM public.catalogue_contracts"))}
                contract_ids = sorted(after - before)
                ids = sorted(stored.saved.contract_ids)
                await paper_store.place(setup, user, stored.id, [
                    paper_store.NewOrder(ids[0], "SELL", 65, D("10.00"), "open", pm.OPEN_AT),
                    paper_store.NewOrder(ids[1], "BUY", 65, D("5.00"), "open", pm.OPEN_AT),
                    paper_store.NewOrder(ids[2], "SELL", 65, D("8.00"), "open", pm.OPEN_AT),
                    paper_store.NewOrder(ids[3], "BUY", 65, D("4.00"), "open", pm.OPEN_AT)])
                await pm._exit_below(setup, stored.id)
            keys = [c.feed_key for c in await tracked_contracts.resolve(setup, ids)]
        provider, _clock, last = _market()  # the route's market: the recorded replay, as every exit test
        app = _app(sessions, user)
        app.dependency_overrides[get_market_context] = lambda: MarketContext(provider, lambda: last, D("0.065"), None)
        app.dependency_overrides[tracking_routes.get_live_feed] = lambda: None
        app.dependency_overrides[get_answer_clock] = lambda: lambda: ANSWERED
        app.dependency_overrides[tracking_routes.get_near_level_threshold] = lambda: D("0.6")

        market = pm.Market()

        async def read_settings():
            async with app_engine.connect() as conn:
                return await settings_store.settings_in_force(conn)
        monitor = paper_monitor.PaperMonitor(sessions, lambda: market.feed, leg_prices=market.leg_prices,
                                             read_settings=read_settings, monotonic=lambda: 0.0)
        reached, go = asyncio.Event(), asyncio.Event()
        if pause_at == "before_claim":
            monkeypatch.setattr(paper_monitor, "triggers", _Pause(triggers, "claim_fire", reached, go))
        else:
            monkeypatch.setattr(paper_monitor, "paper_store", _Pause(paper_store, "place", reached, go))
        fired: list[BaseException] = []
        real_fire = monitor._fire

        async def recording(*args, **kwargs):
            try:
                return await real_fire(*args, **kwargs)
            except BaseException as exc:  # kept for the assertions
                fired.append(exc)
                raise
        monitor._fire = recording
        assert await monitor.step() == 0  # loads and subscribes
        for key, ltp in zip(keys, ["41.00", "12.50", "30.25", "8.75"], strict=True):
            market.tick(key, ltp)
        market.tick(pm.INDEX, "22849.95")

        monitor_task = asyncio.create_task(monitor.step())
        await asyncio.wait_for(reached.wait(), 10)

        async def route_exit():
            async with _client(app) as client:
                return await client.post(f"/strategies/{stored.id}/tracking/exit", json={"legs": [0, 1, 2, 3]})
        route_task = asyncio.create_task(route_exit())
        for _ in range(60):  # until the route is done or waits on a lock held by the paused monitor
            if route_task.done() or await _someone_waits_on_a_lock(app_engine):
                break
            await asyncio.sleep(0.05)
        go.set()
        done = await asyncio.wait_for(asyncio.gather(monitor_task, route_task, return_exceptions=True), 30)
        monitor.close()

        problems = [repr(e) for e in [*fired, *(d for d in done if isinstance(d, BaseException))]]
        assert not [p for p in problems if "deadlock" in p.lower()], problems
        assert problems == [], problems
        assert monitor.failures == 0
        route_reply = done[1]
        assert route_reply.status_code in (OK, CONFLICT), route_reply.text
        if route_reply.status_code == CONFLICT:
            assert route_reply.json()["code"] == _code("tracking_leg_already_exited")  # the loser: stored nothing
        async with app_engine.connect() as conn:
            kinds = (await conn.execute(text("SELECT kind, count(*) FROM public.paper_orders "
                                             "WHERE strategy_id = :s AND kind <> 'open' GROUP BY kind"),
                                        {"s": stored.id})).all()
        assert [tuple(k) for k in kinds] in ([("exit", 4)], [("stop", 4)]), kinds  # exactly one set of closing rows
    finally:
        await _remove_paper_rows(admin_engine, user, contract_ids)


def test_the_old_settle_price_is_gone_the_engine_owns_the_intrinsic_value():
    """R5: ``paper_settlement.settle_price`` is deleted; its caller uses ``ofo.engine.legs.intrinsic_value``."""
    assert not hasattr(ps, "settle_price")
