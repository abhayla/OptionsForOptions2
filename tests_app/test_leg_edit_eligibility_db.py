"""W-158 fix round 1 (REQ-078 AC-6, AC-10; ADR-104): the leg-edit route's REAL move checks run against real PostgreSQL.

The route tests in test_leg_edit_route.py replace ``get_move_eligibility`` and ``get_list_current`` with fakes, so the
real checks never ran (Opus check MAJOR 2). Here the dependencies the route really uses are called, on the recorded
2026-10-08 Zerodha list (the same real rows as test_eligibility_from_zerodha.py) in a transaction that is rolled back.

Answer states: eligibility row tradable -> allowed; not tradable (the contract left the latest list) -> refused; NO
stored row (an id the store does not hold) -> refused, fail closed; no load ever -> refused. Today's list: loaded today
-> current; loaded yesterday -> not current (Shift / Width / Hedge off, ADR-104).
"""

from __future__ import annotations

import datetime

from ofo_app import catalogue_picker as picker
from ofo_app.catalogue_store import apply_update
from ofo_app.routes import leg_edit as route
from sqlalchemy import text
from test_strategy_followups import _ConnMaker
from test_strategy_store import AS_OF, _fixture_rows, _ids

LIST_DAY = AS_OF.date()  # 2026-10-08, the recorded list's day
DB_TODAY = text("SELECT (now() AT TIME ZONE 'Asia/Kolkata')::date")
SATURDAY = 5  # datetime.weekday()
NO_SUCH_CONTRACT = 999_999_999
LISTED_OFF = text("UPDATE public.catalogue_contracts SET currently_listed = FALSE WHERE id = :id")


class _Session(_ConnMaker):
    """The session the route's dependencies open: it hands them the test's own connection (rolled back by the test)."""

    async def connection(self):
        return self.conn


def _wired(monkeypatch, conn, day: datetime.date) -> None:
    """The route's own dependencies, unchanged, reading the test's connection on the given database day."""
    monkeypatch.setattr("ofo_app.db.get_sessionmaker", lambda: _Session(conn))

    async def today(_conn) -> datetime.date:
        return day
    monkeypatch.setattr(picker, "database_today", today)


async def test_the_real_eligibility_check_allows_tradable_refuses_not_tradable_and_refuses_a_missing_row(
        app_engine, monkeypatch):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture_rows(), as_of=AS_OF)
            ids = list(dict.fromkeys((await _ids(conn)).values()))
            first, second = ids[0], ids[1]
            await conn.execute(LISTED_OFF, {"id": first})  # left the latest list: not tradable
            _wired(monkeypatch, conn, LIST_DAY)
            tradable = route.get_move_eligibility()
            assert await tradable([second]) == [True]  # positive control: a listed contract is tradable
            assert await tradable([first]) == [False]  # a stored row that says not tradable
            assert await tradable([NO_SUCH_CONTRACT]) == [False]  # NO stored row: refused (fail closed)
            assert await tradable([second, first, NO_SUCH_CONTRACT]) == [True, False, False]  # per leg, in order
        finally:
            await trans.rollback()


async def test_the_real_eligibility_check_refuses_every_contract_when_no_list_was_ever_loaded(app_engine, monkeypatch):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture_rows(), as_of=AS_OF)
            ids = list(dict.fromkeys((await _ids(conn)).values()))[:2]
            await trans.rollback()  # the same database with nothing loaded: contracts that exist elsewhere are unknown
            trans = await conn.begin()
            _wired(monkeypatch, conn, LIST_DAY)
            assert await route.get_move_eligibility()(ids) == [False, False]
        finally:
            await trans.rollback()


async def test_the_real_list_check_is_current_on_the_loaded_day_and_not_the_day_after(app_engine, monkeypatch):
    """AC-10: the database stamps the load time itself (it cannot be back-dated), so "yesterday's list" is judged
    one day ahead: a list loaded now is today's list today and is yesterday's list tomorrow (the three controls are
    then off); with no load at all it is not current either."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            db_today = (await conn.execute(DB_TODAY)).scalar_one()
            _wired(monkeypatch, conn, db_today)
            assert await route.get_list_current() is False  # nothing loaded in this database
            await apply_update(conn, _fixture_rows(), as_of=AS_OF)
            assert await route.get_list_current() is True  # loaded now, judged today
            next_session_day = db_today + datetime.timedelta(days=1)
            while next_session_day.weekday() >= SATURDAY:  # a weekend judges as Friday 08:30, so judge on a weekday
                next_session_day += datetime.timedelta(days=1)
            _wired(monkeypatch, conn, next_session_day)
            assert await route.get_list_current() is False  # the same load, judged next session day: yesterday's list
        finally:
            await trans.rollback()
