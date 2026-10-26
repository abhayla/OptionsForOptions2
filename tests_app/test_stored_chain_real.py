"""Chain-reader defect (REQ-080 AC-1/AC-2, REQ-029/REQ-030, ADR-132): the REAL ``stored_chain`` against PostgreSQL.

Every route test replaced the reader dependency with a fake, so the real reader never ran in a test and its positional
``ChainCatalogue(expiries, options, permissions)`` put the permission dict into ``unreadable`` (truthy): every real
read said CATALOGUE_UNREADABLE with no rows. Here the reader runs unchanged on the recorded 2026-10-08 Zerodha list in a
transaction that is rolled back (the same wiring as test_leg_edit_eligibility_db.py).

Answer states: readable catalogue -> contracts, permissions keyed by instrument_id; database error -> unreadable True
with no rows; the asked expiry not in the catalogue -> readable, no contracts.
"""

from __future__ import annotations

import dataclasses
import datetime

import pytest
from httpx import ASGITransport, AsyncClient
from ofo_app import catalogue_picker as picker
from ofo_app import chain_push
from ofo_app.catalogue_store import apply_update
from ofo_app.chain_push import ChainCatalogue, stored_chain
from ofo_app.routes import leg_picker, outcome
from sqlalchemy.exc import OperationalError
from test_strategy_followups import _ConnMaker
from test_strategy_store import AS_OF, EXPIRY, _fixture_rows

LIST_DAY = AS_OF.date()
CLOCK = datetime.datetime(2026, 10, 8, 9, 20, tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
HTTP_OK = 200


class _Session(_ConnMaker):
    async def connection(self):
        return self.conn


def _wired(monkeypatch, conn) -> None:
    monkeypatch.setattr("ofo_app.db.get_sessionmaker", lambda: _Session(conn))

    async def today(_conn) -> datetime.date:
        return LIST_DAY
    monkeypatch.setattr(picker, "database_today", today)


async def test_the_real_reader_returns_a_readable_catalogue_with_permissions(app_engine, monkeypatch):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture_rows(), as_of=AS_OF)
            _wired(monkeypatch, conn)
            catalogue = await stored_chain("NIFTY", EXPIRY)
            assert catalogue.unreadable is False
            assert EXPIRY in catalogue.expiries and catalogue.contracts
            assert catalogue.permissions, "no contract was ever permitted"
            assert set(catalogue.permissions) == {c.instrument_id for c in catalogue.contracts}
            assert set(catalogue.permissions.values()) == {"permitted"}  # the recorded list: all listed
            unknown = await stored_chain("NIFTY", datetime.date(2031, 1, 1))  # expiry not held: readable, empty
            assert (unknown.unreadable, unknown.contracts, dict(unknown.permissions)) == (False, (), {})
        finally:
            await trans.rollback()


async def test_a_database_error_is_unreadable_with_no_rows(monkeypatch):
    def boom():
        raise OperationalError("select", {}, OSError("refused"))
    monkeypatch.setattr("ofo_app.db.get_sessionmaker", boom)
    catalogue = await stored_chain("NIFTY", EXPIRY)
    assert (catalogue.unreadable, catalogue.contracts, catalogue.expiries) == (True, (), ())
    assert not catalogue.permissions


async def test_the_strikes_route_lists_strikes_through_the_real_reader(app_engine, monkeypatch):
    from ofo_app.main import create_app  # noqa: PLC0415 - built per test, no lifespan

    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture_rows(), as_of=AS_OF)
            _wired(monkeypatch, conn)
            app = create_app()
            app.dependency_overrides[leg_picker.get_feed] = lambda: None  # NOT get_picker_reader: the reader is real
            app.dependency_overrides[outcome.get_answer_clock] = lambda: (lambda: CLOCK)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
                got = await client.get("/api/leg-picker/strikes",
                                       params={"underlying": "NIFTY", "expiry": EXPIRY.isoformat()})
            assert got.status_code == HTTP_OK, got.text
            body = got.json()
            assert body["reason"] != "CATALOGUE_UNREADABLE" and body["rows"], body
        finally:
            await trans.rollback()


def test_a_catalogue_cannot_be_built_positionally():
    for cls in (chain_push.ChainCatalogue, leg_picker.FuturesCatalogue):
        assert dataclasses.is_dataclass(cls)
        with pytest.raises(TypeError):
            cls((), (), True)
    assert ChainCatalogue(expiries=(), contracts=()).unreadable is False
