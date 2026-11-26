"""D-51 (ADR-330 (43), REQ-091 AC-8): the Strategy Chart draws what is OPEN on the strategy, from the one door
(``ofo_app.open_legs``), not the saved definition. DB-free: the store, the book and the contract resolver are in-memory
answers; the route, the door, the engine and the Kite transport (the real recorded F-64 bodies, see
test_strategy_price_history_route) run for real. The saved plan is the 4-leg condor; the book opened all four at 65
units, and the extra orders close some of them."""
from __future__ import annotations

import datetime
from decimal import Decimal
from http import HTTPStatus
from types import SimpleNamespace

from httpx import ASGITransport, AsyncClient
from ofo.engine.legs import Action
from ofo.timeutil import IST
from ofo_app import catalogue_store, held_switches, paper_store, tracked_contracts
from ofo_app import strategy_store as store
from ofo_app.db import get_db
from test_strategy_price_history_route import _app_with, _fresh_cache, _standard, _token  # noqa: F401 - autouse fixture
from test_strategy_store import WING, _client, _fixture_rows, _user

CONDOR_SYMBOLS = ["NIFTY26O1322800CE", "NIFTY26O1323000CE", "NIFTY26O1322400PE", "NIFTY26O1322200PE"]
CONDOR_SIDES = ["SELL", "BUY", "SELL", "BUY"]
PLACED = datetime.datetime(2026, 10, 14, 9, 20, tzinfo=IST)
OPPOSITE = {"BUY": "SELL", "SELL": "BUY"}


class _FakeDb:
    async def commit(self):
        return None

    async def rollback(self):
        return None


def _order(oid, cid, side, kind, price="100.00"):
    new = paper_store.NewOrder(cid, side, 65, Decimal(price), kind, PLACED)
    return paper_store.StoredOrder(oid, 77, new, PLACED)


def _book(*closed: int):
    """Opens all four legs (as the plan says), then exits the legs numbered in ``closed`` (1-based)."""
    orders = [_order(i, i, side, "open") for i, side in enumerate(CONDOR_SIDES, start=1)]
    orders += [_order(10 + c, c, OPPOSITE[CONDOR_SIDES[c - 1]], "exit", "90.00") for c in closed]
    return orders


def _wire(monkeypatch, book, *, fail=False):
    rows = {r.ref("zerodha").broker_symbol: r for r in _fixture_rows(CONDOR_SYMBOLS)}
    found = {i: tracked_contracts.TrackedContract(
        i, tracked_contracts.LIVE, catalogue_store.StoredContract(i, rows[s], True, False, False, None))
        for i, s in enumerate(CONDOR_SYMBOLS, start=1)}
    user = _user()
    legs = [SimpleNamespace(action=Action(s), quantity=65) for s in CONDOR_SIDES]
    plan = SimpleNamespace(id=77, user_ref=user, saved=SimpleNamespace(
        definition=SimpleNamespace(legs=legs, underlying="NIFTY"), contract_ids=(1, 2, 3, 4)))

    async def load(_db, _user_ref, _sid):
        return plan

    async def book_load(_db, _sid):
        if fail:
            raise RuntimeError("the book could not be read")
        return tuple(book)

    async def resolve(_db, ids):
        return tuple(found[i] for i in ids)

    monkeypatch.setattr(store, "load", load)
    monkeypatch.setattr(paper_store, "load", book_load)
    monkeypatch.setattr(tracked_contracts, "resolve", resolve)
    return user


def _offline(user, seen):
    app = _app_with(None, user, transport=_standard(seen))

    async def _db():
        yield _FakeDb()

    app.dependency_overrides[get_db] = _db
    return app


def _fetched_tokens(seen):
    return sorted(u.split("/historical/")[1].split("/", maxsplit=1)[0] for u in seen)


async def test_a_running_trade_after_one_exit_charts_the_remaining_legs_only(monkeypatch):
    user = _wire(monkeypatch, _book(1))
    seen: list[str] = []
    async with _client(_offline(user, seen)) as ac:
        resp = await ac.get("/strategies/77/price-history")
    assert resp.status_code == HTTPStatus.OK, resp.text
    assert resp.json()["available"] is True and resp.json()["state"] == "available"
    assert _fetched_tokens(seen) == sorted(_token(s) for s in [*CONDOR_SYMBOLS[1:], WING])  # 3 open legs + the future
    assert _token(CONDOR_SYMBOLS[0]) not in "".join(seen)  # the closed SELL 22800 CE is never fetched


async def test_a_trade_with_nothing_placed_charts_its_plan(monkeypatch):
    user = _wire(monkeypatch, [])
    seen: list[str] = []
    async with _client(_offline(user, seen)) as ac:
        resp = await ac.get("/strategies/77/price-history")
    assert resp.json()["available"] is True
    assert len(seen) == len(CONDOR_SYMBOLS) + 1  # 4 plan legs + the future


async def test_every_leg_closed_answers_no_open_legs_and_reads_no_prices(monkeypatch):
    user = _wire(monkeypatch, _book(1, 2, 3, 4))
    seen: list[str] = []
    async with _client(_offline(user, seen)) as ac:
        resp = await ac.get("/strategies/77/price-history")
    body = resp.json()
    assert resp.status_code == HTTPStatus.OK
    assert (body["available"], body["state"], body["points"]) == (False, "no_open_legs", [])
    assert body["reason"] == "This strategy has no open legs, so there is no strategy chart." and seen == []


async def test_a_failed_book_read_refuses_and_never_charts_the_saved_legs(monkeypatch):
    user = _wire(monkeypatch, _book(), fail=True)
    seen: list[str] = []
    transport = ASGITransport(app=_offline(user, seen), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://t") as ac:
        resp = await ac.get("/strategies/77/price-history")
    assert resp.status_code >= HTTPStatus.BAD_REQUEST and seen == []
    assert '"available"' not in resp.text


async def test_the_switch_off_answer_is_unchanged(monkeypatch):
    user = _wire(monkeypatch, _book())
    monkeypatch.setattr(held_switches, "held_on", lambda name, environ=None: False)
    seen: list[str] = []
    async with _client(_offline(user, seen)) as ac:
        resp = await ac.get("/strategies/77/price-history")
    assert resp.status_code == HTTPStatus.CONFLICT and "The strategy chart is not available." in resp.text
    assert seen == []
