"""GC-TRACK1 k07 (ADR-292 (1)(2), ADR-290 (2), REQ-109 AC-1): a strategy entered "held at my broker".

Core proof (DB, fresh database): four `open` orders with a `held` block on a fresh strategy are stored as orders AND
one held row (entry_at = the stated time, created_at later), read back from the database, not from the reply.
Answer states of the input: absent / valid / later than now / after the earliest leg expiry / no offset / strategy not
fresh or an order not `open` / broker blank, too long, line break / the held insert fails (whole basket rolls back).
The saved strategy is test_strategy_store's iron condor (65 units a leg, expiry 2026-10-13); the clock is 2026-10-08.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from http import HTTPStatus

import pytest
from ofo_app import held_entry_store
from ofo_app.routes.outcome import get_answer_clock
from sqlalchemy import text
from test_strategy_store import _client
from test_strategy_tracking import ANSWERED, ENTRY_PRICES, _paper_body, _setup

ENTERED = datetime.datetime(2026, 10, 5, 4, 0, tzinfo=datetime.UTC)
_HELD = text("SELECT entry_at, broker_text, created_at FROM public.strategy_held_entries WHERE strategy_id = :i")
_ORDERS = text("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :i")


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


def _held_body(stored, held: dict | None) -> dict:
    body = _paper_body(stored, ENTRY_PRICES)
    if held is not None:
        body["held"] = held
    return body


async def _post(app, stored, body):
    async with _client(app) as c:
        return await c.post(f"/paper/strategies/{stored.id}/orders", json=body)


async def _stored(db, strategy_id: int) -> tuple[int, list]:
    orders = (await db.execute(_ORDERS, {"i": strategy_id})).scalar_one()
    return int(orders), (await db.execute(_HELD, {"i": strategy_id})).all()


async def test_held_condor_saved_with_its_stated_entry(db):
    app, stored, *_ = await _setup(db)
    reply = await _post(app, stored, _held_body(stored, {"entry_at": ENTERED.isoformat(), "broker": "  Upstox "}))
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    orders, rows = await _stored(db, stored.id)
    assert orders == 4  # noqa: PLR2004 - four legs
    assert len(rows) == 1
    assert rows[0].entry_at == ENTERED
    assert rows[0].broker_text == "Upstox"
    assert rows[0].created_at > rows[0].entry_at


async def test_absent_held_is_a_plain_paper_basket(db):
    app, stored, *_ = await _setup(db)
    reply = await _post(app, stored, _held_body(stored, None))
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    assert await _stored(db, stored.id) == (4, [])


async def test_entry_later_than_now_is_422_and_nothing_is_stored(db):
    app, stored, *_ = await _setup(db)
    later = ANSWERED + datetime.timedelta(minutes=1)
    reply = await _post(app, stored, _held_body(stored, {"entry_at": later.isoformat()}))
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, reply.text
    assert "later than now" in reply.text
    assert await _stored(db, stored.id) == (0, [])


async def test_entry_after_the_earliest_leg_expiry_is_422_and_names_the_expiry(db):
    app, stored, *_ = await _setup(db)
    now = datetime.datetime(2026, 10, 14, 5, 0, tzinfo=datetime.UTC)  # a day after the expiry, market hours
    app.dependency_overrides[get_answer_clock] = lambda: lambda: now
    after = datetime.datetime(2026, 10, 13, 18, 30, tzinfo=datetime.UTC)  # 14 Oct 00:00 IST
    reply = await _post(app, stored, _held_body(stored, {"entry_at": after.isoformat()}))
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, reply.text
    assert "after the expiry" in reply.text
    assert "13 Oct 2026" in reply.text
    assert await _stored(db, stored.id) == (0, [])


async def test_entry_on_the_expiry_day_in_ist_is_accepted(db):
    app, stored, *_ = await _setup(db)
    now = datetime.datetime(2026, 10, 13, 5, 0, tzinfo=datetime.UTC)
    app.dependency_overrides[get_answer_clock] = lambda: lambda: now
    on_day = datetime.datetime(2026, 10, 13, 3, 45, tzinfo=datetime.UTC)  # 13 Oct 09:15 IST
    reply = await _post(app, stored, _held_body(stored, {"entry_at": on_day.isoformat()}))
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    assert (await _stored(db, stored.id))[0] == 4  # noqa: PLR2004


async def test_entry_without_an_offset_is_422(db):
    app, stored, *_ = await _setup(db)
    reply = await _post(app, stored, _held_body(stored, {"entry_at": "2026-10-05T09:30:00"}))
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, reply.text
    assert await _stored(db, stored.id) == (0, [])


async def test_a_strategy_that_already_has_orders_refuses_the_held_block(db):
    app, stored, *_ = await _setup(db)
    assert (await _post(app, stored, _held_body(stored, None))).status_code == HTTPStatus.CREATED
    reply = await _post(app, stored, _held_body(stored, {"entry_at": ENTERED.isoformat()}))
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, reply.text
    assert await _stored(db, stored.id) == (4, [])


async def test_an_order_that_is_not_open_refuses_the_held_block(db):
    app, stored, *_ = await _setup(db)
    body = _held_body(stored, {"entry_at": ENTERED.isoformat()})
    body["orders"][0]["kind"] = "exit"
    reply = await _post(app, stored, body)
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, reply.text
    assert await _stored(db, stored.id) == (0, [])


async def test_a_blank_broker_is_stored_as_null(db):
    app, stored, *_ = await _setup(db)
    reply = await _post(app, stored, _held_body(stored, {"entry_at": ENTERED.isoformat(), "broker": "   "}))
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    rows = (await _stored(db, stored.id))[1]
    assert len(rows) == 1
    assert rows[0].broker_text is None


@pytest.mark.parametrize("broker", ["x" * 41, "Up\nstox", "Up\rstox"])
async def test_a_long_or_multi_line_broker_is_422(db, broker):
    app, stored, *_ = await _setup(db)
    reply = await _post(app, stored, _held_body(stored, {"entry_at": ENTERED.isoformat(), "broker": broker}))
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, reply.text
    assert await _stored(db, stored.id) == (0, [])


async def test_a_failing_held_insert_rolls_the_whole_basket_back(db, monkeypatch):
    app, stored, *_ = await _setup(db)

    async def boom(*_a, **_k):
        raise RuntimeError("held insert failed")

    monkeypatch.setattr(held_entry_store, "record", boom)
    reply = await _post(app, stored, _held_body(stored, {"entry_at": ENTERED.isoformat()}))
    assert reply.status_code == HTTPStatus.INTERNAL_SERVER_ERROR, reply.text  # the error boundary answers
    assert await _stored(db, stored.id) == (0, [])


# ---- GC-TRACK1 k07 read side: the paper replies say a strategy is held, and when its rules start ----
_CLOCK0 = text("SELECT clock FROM public.strategy_basket_facts WHERE strategy_id = :i AND basket_no = 0")


async def _get(app, path):
    async with _client(app) as c:
        return await c.get(path)


async def _listed(app, strategy_id):
    reply = await _get(app, "/paper/strategies")
    assert reply.status_code == HTTPStatus.OK, reply.text
    return next(s for s in reply.json()["strategies"] if s["strategy_id"] == strategy_id)


async def test_held_shows_in_the_book_and_the_list_with_the_stored_rules_start(db):
    app, stored, *_ = await _setup(db)
    assert (await _post(app, stored, _held_body(stored, {"entry_at": ENTERED.isoformat(), "broker": "Upstox"}))
            ).status_code == HTTPStatus.CREATED
    clock = (await db.execute(_CLOCK0, {"i": stored.id})).scalar_one()  # read from the database, not the reply
    book = await _get(app, f"/paper/strategies/{stored.id}")
    assert book.status_code == HTTPStatus.OK, book.text
    for held in (book.json()["held"], (await _listed(app, stored.id))["held"]):
        assert held["source"] == "held_elsewhere"
        assert datetime.datetime.fromisoformat(held["entry_at"]) == ENTERED
        assert held["broker"] == '"Upstox"'  # quoted user text, like a strategy name
        assert datetime.datetime.fromisoformat(held["rules_start_at"]) == clock


async def test_a_plain_paper_strategy_has_held_null(db):
    app, stored, *_ = await _setup(db)
    assert (await _post(app, stored, _held_body(stored, None))).status_code == HTTPStatus.CREATED
    assert (await _get(app, f"/paper/strategies/{stored.id}")).json()["held"] is None
    assert (await _listed(app, stored.id))["held"] is None


async def test_held_without_a_facts_row_has_rules_start_null(db, monkeypatch):
    app, stored, *_ = await _setup(db)

    async def no_facts(*_a, **_k):  # the fill facts are skipped (finding: entry-facts-skipped-when-no-index-quote)
        return None

    monkeypatch.setattr("ofo_app.adjustment_readers.record_basket_facts", no_facts)
    assert (await _post(app, stored, _held_body(stored, {"entry_at": ENTERED.isoformat()}))
            ).status_code == HTTPStatus.CREATED
    assert (await db.execute(_CLOCK0, {"i": stored.id})).first() is None
    held = (await _get(app, f"/paper/strategies/{stored.id}")).json()["held"]
    assert held["rules_start_at"] is None
    assert held["broker"] is None


async def test_a_failing_held_read_fails_the_reply(db, monkeypatch):
    app, stored, *_ = await _setup(db)
    assert (await _post(app, stored, _held_body(stored, {"entry_at": ENTERED.isoformat()}))
            ).status_code == HTTPStatus.CREATED

    async def boom(*_a, **_k):
        raise RuntimeError("held read failed")

    monkeypatch.setattr(held_entry_store, "read_many", boom)
    assert (await _get(app, f"/paper/strategies/{stored.id}")).status_code == HTTPStatus.INTERNAL_SERVER_ERROR


# ---- k07 review fixes ----
async def test_a_basket_landing_second_never_gets_the_held_row(db, monkeypatch):
    """(a) the route's first-basket check ran before the store's lock: simulate the race (the route sees an empty
    book, the store sees the first basket already there)."""
    app, stored, *_ = await _setup(db)
    assert (await _post(app, stored, _held_body(stored, None))).status_code == HTTPStatus.CREATED

    async def empty(*_a, **_k):
        return set()

    monkeypatch.setattr("ofo_app.routes.paper.paper_store.tracked_ids", empty)
    reply = await _post(app, stored, _held_body(stored, {"entry_at": ENTERED.isoformat()}))
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, reply.text
    assert await _stored(db, stored.id) == (4, [])  # the second basket was rolled back too


@pytest.mark.parametrize("char", [chr(0x2028), chr(0x2029), chr(0x85), chr(0x0B), chr(0x0C)])
async def test_other_line_break_characters_in_the_broker_are_422(db, char):
    app, stored, *_ = await _setup(db)
    reply = await _post(app, stored, _held_body(stored, {"entry_at": ENTERED.isoformat(), "broker": f"Up{char}stox"}))
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, reply.text
    assert await _stored(db, stored.id) == (0, [])


async def test_an_add_order_with_a_held_block_is_422(db):
    app, stored, *_ = await _setup(db)
    body = _held_body(stored, {"entry_at": ENTERED.isoformat()})
    body["orders"][0]["kind"] = "add"  # the store accepts an add of a new side; only the held kind check refuses it
    reply = await _post(app, stored, body)
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, reply.text
    assert await _stored(db, stored.id) == (0, [])


# ---- GC-TRACK1 k09: broker changes are recorded with the existing exit and add forms (no new code) ----
async def test_exit_and_add_orders_on_a_held_condor_move_the_figures_and_leave_the_held_row(db):
    app, stored, *_ = await _setup(db)
    assert (await _post(app, stored, _held_body(stored, {"entry_at": ENTERED.isoformat(), "broker": "Upstox"}))
            ).status_code == HTTPStatus.CREATED
    held_before = (await _stored(db, stored.id))[1]
    sold_call, bought_call = stored.saved.contract_ids[:2]
    leg = {"side": "BUY", "quantity": 65}
    out = await _post(app, stored, {"orders": [{"contract_id": sold_call, "kind": "exit", "price": "1.00", **leg}]})
    assert out.status_code == HTTPStatus.CREATED, out.text
    exit_price = D(out.json()["orders"][-1]["price"])  # an exit's price is the server's, as for any paper book
    pos = {p["contract_id"]: p for p in out.json()["positions"]}[sold_call]
    assert pos["net_quantity"] == 0
    assert D(pos["booked"]) == (D(ENTRY_PRICES[0]) - exit_price) * 65  # sold at the entry price, bought back
    added = await _post(app, stored, {"orders": [{"contract_id": bought_call, "kind": "add", "price": "13.00",
                                                  **leg}]})
    assert added.status_code == HTTPStatus.CREATED, added.text
    assert {p["contract_id"]: p["net_quantity"] for p in added.json()["positions"]}[bought_call] == 130  # noqa: PLR2004
    assert added.json()["orders"][-1]["price"] == "13.00"  # the typed price is the stored price
    assert await _stored(db, stored.id) == (6, held_before)  # four legs + exit + add; the held row is unchanged
    assert added.json()["held"]["broker"] is not None
