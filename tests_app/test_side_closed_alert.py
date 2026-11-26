"""ADR-330 (2) (b), P7: the side_closed alert of the 25 Nov 2026 iron condor after its two call legs exited.

The alert is raised once through ``actionable_alerts`` (never its own code), stays open until answered, and no answer
places an order: ``add_legs`` stores the answer only, ``confirm_new_shape`` makes the shape label "Bull Put Spread".
Every test runs in a rolled-back transaction as the limited app role.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from ofo import alerts as kinds
from ofo.adjustment.approaches import Position, PositionLeg
from ofo.timeutil import IST
from ofo_app import actionable_alerts as aa
from ofo_app import background, side_closed
from sqlalchemy import text
from test_strategy_store import _user, _with_draft

D = Decimal
EXPIRY = datetime.date(2026, 12, 1)
AT = datetime.datetime(2026, 11, 25, 11, 2, 20, tzinfo=IST)
LATER = datetime.datetime(2026, 11, 25, 12, 0, 0, tzinfo=IST)
CONDOR = (("SELL", "CE", 24500), ("BUY", "CE", 24700), ("SELL", "PE", 24000), ("BUY", "PE", 23800))
BULL_PUT = "Bull Put Spread"
BEAR_CALL = "Bear Call Spread"


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


def _legs(rows):
    return tuple(PositionLeg(s, k, D(x), EXPIRY, 1, D(50), f"N{x}{k}") for s, k, x in rows)


def _tracked(open_rows):
    def pos(rows):
        return Position("NIFTY", 65, "weekly", datetime.date.min, _legs(rows))
    return SimpleNamespace(entry_position=pos(CONDOR), position=pos(open_rows))


CALL_EXITED = _tracked(CONDOR[2:])
PUT_EXITED = _tracked(CONDOR[:2])


async def _orders(conn, sid) -> int:
    return (await conn.execute(text("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :i"),
                               {"i": sid})).scalar_one()


async def _name(conn, sid) -> str:
    return (await conn.execute(text("SELECT name FROM public.strategies WHERE id = :i"), {"i": sid})).scalar_one()


async def _setup(conn):
    user = _user()
    _, stored = await _with_draft(conn, user)
    return user, stored.id


async def test_call_side_closed_raises_one_open_alert_and_changes_no_name(db):
    user, sid = await _setup(db)
    name, orders = await _name(db, sid), await _orders(db, sid)
    first = await side_closed.raise_if_closed(db, user, sid, CALL_EXITED, at=AT)
    again = await side_closed.raise_if_closed(db, user, sid, CALL_EXITED, at=LATER)
    rows = await aa.unanswered(db, user)
    assert first is not None and again is None
    assert [(r.id, r.kind, r.rule_id, r.outcome) for r in rows] == [
        (first, kinds.SIDE_CLOSED, "side.closed.call", "open")]
    assert await aa.unanswered_count(db, user) == 1
    assert await _name(db, sid) == name and await side_closed.confirmed_shape(db, user, sid) is None
    assert await _orders(db, sid) == orders


async def test_confirm_new_shape_stores_the_label(db):
    user, sid = await _setup(db)
    orders = await _orders(db, sid)
    alert = await side_closed.raise_if_closed(db, user, sid, CALL_EXITED, at=AT)
    done = await aa.answer(db, user, alert, kinds.CONFIRM_NEW_SHAPE, LATER)
    assert done.outcome == "dismissed" and done.answer == kinds.CONFIRM_NEW_SHAPE
    assert await side_closed.confirmed_shape(db, user, sid) == BULL_PUT
    assert await aa.unanswered(db, user) == []
    # the plan, its type and the stored strategy name are untouched; the answered row is not raised again
    assert await side_closed.raise_if_closed(db, user, sid, CALL_EXITED, at=LATER) is None
    assert await _orders(db, sid) == orders


async def test_add_legs_stores_the_answer_and_places_no_order(db):
    user, sid = await _setup(db)
    name, orders = await _name(db, sid), await _orders(db, sid)
    alert = await side_closed.raise_if_closed(db, user, sid, CALL_EXITED, at=AT)
    done = await aa.answer(db, user, alert, kinds.ADD_LEGS, LATER)
    assert done.answer == kinds.ADD_LEGS and done.outcome == "acted_on"
    assert await side_closed.confirmed_shape(db, user, sid) is None  # the entry shape name stands
    assert await _name(db, sid) == name and await _orders(db, sid) == orders


async def test_put_side_closed_names_bear_call_spread(db):
    user, sid = await _setup(db)
    alert = await side_closed.raise_if_closed(db, user, sid, PUT_EXITED, at=AT)
    await aa.answer(db, user, alert, kinds.CONFIRM_NEW_SHAPE, LATER)
    assert await side_closed.confirmed_shape(db, user, sid) == BEAR_CALL


async def test_an_exit_answer_is_refused_and_the_row_stays_open(db):
    user, sid = await _setup(db)
    alert = await side_closed.raise_if_closed(db, user, sid, CALL_EXITED, at=AT)
    with pytest.raises(aa.AlertAnswerRefused):
        await aa.answer(db, user, alert, kinds.EXIT, LATER)
    assert [r.id for r in await aa.unanswered(db, user)] == [alert]


@pytest.mark.parametrize("tracked", [
    _tracked(CONDOR),  # nothing exited
    _tracked(CONDOR[1:]),  # one leg of a side exited
    _tracked(()),  # every leg exited: the strategy is closed, P1 closes its alerts
    _tracked(CONDOR[:1] + CONDOR[2:]),  # one call leg exited, the other side whole
    SimpleNamespace(entry_position=None, position=None),  # unreadable
])
async def test_no_notice_when_no_side_is_closed(db, tracked):
    user, sid = await _setup(db)
    assert await side_closed.raise_if_closed(db, user, sid, tracked, at=AT) is None
    assert await aa.unanswered(db, user) == []


async def test_a_position_change_does_not_close_the_alert(db):
    user, sid = await _setup(db)
    alert = await side_closed.raise_if_closed(db, user, sid, CALL_EXITED, at=AT)
    # the worker's next list sees a changed position (an adjustment): the open row stays (P1)
    assert await side_closed.raise_if_closed(db, user, sid, _tracked(CONDOR[2:3] + CONDOR[3:]), at=LATER) is None
    assert [r.id for r in await aa.unanswered(db, user)] == [alert]


async def test_condor_shape_only(db):
    user, sid = await _setup(db)
    wide = SimpleNamespace(entry_position=Position("NIFTY", 65, "weekly", datetime.date.min, _legs(CONDOR[:3])),
                           position=Position("NIFTY", 65, "weekly", datetime.date.min, _legs(CONDOR[2:3])))
    assert await side_closed.raise_if_closed(db, user, sid, wide, at=AT) is None  # not entered as a condor


REVERSE_CONDOR = (("BUY", "CE", 24500), ("SELL", "CE", 24700), ("BUY", "PE", 24000), ("SELL", "PE", 23800))
BUTTERFLY = (("SELL", "CE", 24500), ("BUY", "CE", 24700), ("SELL", "PE", 24500), ("BUY", "PE", 24300))
SHORT_CONDOR_WIDE = (("SELL", "CE", 24500), ("BUY", "CE", 24700), ("SELL", "PE", 24000), ("BUY", "PE", 23800))


def _entered(rows, left):
    def pos(r):
        return Position("NIFTY", 65, "weekly", datetime.date.min, _legs(r))
    return SimpleNamespace(entry_position=pos(rows), position=pos(left))


@pytest.mark.parametrize("rows", [REVERSE_CONDOR, BUTTERFLY])
async def test_only_a_short_condor_is_a_condor(db, rows):
    """Reverse (long) condor and butterfly: no alert; the wings must sit outside the shorts."""
    user, sid = await _setup(db)
    assert await side_closed.raise_if_closed(db, user, sid, _entered(rows, rows[2:]), at=AT) is None
    assert await aa.unanswered(db, user) == []


async def test_a_short_condor_with_wings_outside_raises(db):
    user, sid = await _setup(db)
    got = await side_closed.raise_if_closed(db, user, sid, _entered(SHORT_CONDOR_WIDE, SHORT_CONDOR_WIDE[2:]), at=AT)
    assert got is not None


async def test_a_system_closed_row_does_not_stop_a_new_raise(db):
    user, sid = await _setup(db)
    first = await side_closed.raise_if_closed(db, user, sid, CALL_EXITED, at=AT)
    closed = await aa.close_by_system(db, user, sid, "not_monitored", at=LATER)
    assert [c.id for c in closed] == [first] and await aa.unanswered(db, user) == []
    again = await side_closed.raise_if_closed(db, user, sid, CALL_EXITED, at=LATER)
    assert again is not None and again != first
    assert [r.id for r in await aa.unanswered(db, user)] == [again]


def test_the_worker_has_the_hook():
    assert callable(background.DbGateStore.raise_side_closed)
