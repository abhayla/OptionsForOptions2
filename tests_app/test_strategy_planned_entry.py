"""Issue #208 / REQ-038 AC-5 / ADR-075: Save Draft keeps each leg's planned entry price and its capture time.

Spec basis (quoted): REQ-038 AC-5 "Each leg's planned entry price and its capture time are part of the definition and
are saved with it (ADR-075)." ADR-075 "Save Draft stores each leg's planned entry price and its capture time with the
strategy definition, and a reopened draft shows exactly those; they change only when the user asks to reprice (ADR-068
item 1)." and "LTP, bid, ask, IV and health stay out of the stored strategy (ADR-062 unchanged for live prices)."

Real values: the 2026-10-15 live gate condor (ADR-075 source: draft 948, entries 44.90 / 11.75 / 79.05 / 37.15), put
on the four Iron Condor contracts of tests/fixtures/kite_ws/instruments-2026-10-08-subscribed.csv (test_strategy_store
uses the same rows). The capture time below is one IST time on 2026-10-15; the brief records the entries, not the
second they were captured, so the time is a stand-in for "one capture time", not a recorded value.

Every test runs in a rolled-back transaction (API calls join it through a savepoint session).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from ofo.engine.legs import Action
from ofo.strategy import stored_form as sf
from ofo_app import strategy_store as store
from ofo_app.catalogue_store import apply_update
from ofo_app.db import get_db
from ofo_app.main import create_app
from ofo_app.routes import strategies as strategy_routes

from test_strategy_store import AS_OF, IRON_CONDOR, LOT, _fixture_rows, _ids  # the same real rows

IST = timezone(timedelta(hours=5, minutes=30))
CAPTURED = "2026-10-15T11:02:17+05:30"
CAPTURED_AT = datetime(2026, 10, 15, 11, 2, 17, tzinfo=IST)
ENTRIES = ("44.90", "11.75", "79.05", "37.15")  # ADR-075's source line, in Iron Condor leg order
REPRICED = ("46.10", "12.05", "77.80", "36.40")
REPRICED_AT = "2026-10-15T13:45:00+05:30"
CHECK_VIOLATION = "23514"
INSERT = ("INSERT INTO public.strategies (user_ref, underlying, definition, definition_schema_version) "
          "VALUES (:u, 'NIFTY', CAST(:d AS JSONB), 1)")


def _user() -> str:
    return "test-" + uuid.uuid4().hex


def _legs(ids: list[tuple[int, str, int]], entries=ENTRIES, captured: str | None = CAPTURED) -> list[dict]:
    out = []
    for (contract_id, side, lot), entry in zip(ids, entries):
        leg = {"contract_id": contract_id, "action": side, "quantity": lot}
        if entry is not None:
            leg |= {"planned_entry": entry, "captured_at": captured}
        out.append(leg)
    return out


def _body(ids: list[tuple[int, str, int]], **kw) -> dict:
    extra = {k: kw.pop(k) for k in list(kw) if k == "expected_revision"}
    return {"underlying": "NIFTY", "legs": _legs(ids, **kw), "rules_ref": None, "risk_limits": {},
            "preferences": {}} | extra


def _client(conn, user: str) -> AsyncClient:
    app = create_app()

    async def _db():
        async with AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False) as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[strategy_routes.current_user_ref] = lambda: user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


_LIVE_CONDOR = text(
    "WITH e AS (SELECT min(expiry) AS d FROM public.catalogue_contracts WHERE name = 'NIFTY' AND NOT retired "
    "AND NOT delisted AND instrument_type = 'CE') "
    "SELECT id, instrument_type, strike FROM public.catalogue_contracts, e WHERE name = 'NIFTY' "
    "AND NOT retired AND NOT delisted AND expiry = e.d AND instrument_type IN ('CE', 'PE') ORDER BY strike, id")


async def _catalogue(conn) -> list[tuple[int, str, int]]:
    """(contract id, side, units) for the four condor legs, in IRON_CONDOR order (SELL CE, BUY CE, SELL PE, BUY PE).
    An empty catalogue (CI) gets the fixture rows; a database that already holds the real catalogue (the shared test
    database, where loading the fixture would drop 94% of the live contracts and is refused, ADR-058) gives a condor
    from its own nearest live NIFTY expiry: the two middle-strike calls and puts."""
    savepoint = await conn.begin_nested()
    try:
        await apply_update(conn, _fixture_rows(), as_of=AS_OF)
    except ValueError:
        await savepoint.rollback()
        rows = (await conn.execute(_LIVE_CONDOR)).all()
        calls = [r for r in rows if r.instrument_type == "CE"]
        puts = [r for r in rows if r.instrument_type == "PE"]
        c, p = calls[len(calls) // 2:len(calls) // 2 + 2], puts[len(puts) // 2 - 2:len(puts) // 2]
        picked = [(int(c[0].id), "SELL"), (int(c[1].id), "BUY"), (int(p[1].id), "SELL"), (int(p[0].id), "BUY")]
        resolve = await store.catalogue_resolver(conn, [i for i, _ in picked])
        return [(i, side, resolve(i).lot_size) for i, side in picked]
    await savepoint.commit()
    ids = await _ids(conn)
    return [(ids[symbol], side, LOT) for symbol, side, *_ in IRON_CONDOR]


def _entry_pairs(definition: dict) -> list[tuple]:
    return [(leg.get("planned_entry"), leg.get("captured_at")) for leg in definition["legs"]]


async def _expect_refused(conn, sql: str, params: dict) -> str | None:
    savepoint = await conn.begin_nested()
    try:
        await conn.execute(text(sql), params)
    except DBAPIError as exc:
        await savepoint.rollback()
        return getattr(exc.orig, "sqlstate", None)
    await savepoint.rollback()
    return None


# ---------------------------------------------------------------------------------------------------------------
# Core proof: save -> reload equal, entries and capture time per leg
# ---------------------------------------------------------------------------------------------------------------


async def test_ac5_a_saved_draft_reloads_with_its_planned_entries_and_capture_time(app_engine):
    """AC-5 (ADR-075): POST /strategies with the 2026-10-15 condor's entries, then GET: every leg's planned entry and
    capture time equal the saved ones, as strings in the API and exact Decimal / aware datetime in the store."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids = await _catalogue(conn)
            user = _user()
            async with _client(conn, user) as ac:
                saved = await ac.post("/strategies", json=_body(ids))
                assert saved.status_code == 201, saved.text
                strategy_id = saved.json()["id"]
                got = await ac.get(f"/strategies/{strategy_id}")
            assert got.status_code == 200, got.text
            expected = [(e, CAPTURED) for e in ENTRIES]
            assert _entry_pairs(saved.json()["definition"]) == expected
            assert _entry_pairs(got.json()["definition"]) == expected
            loaded = await store.load(conn, user, strategy_id)
            assert loaded.saved.entries == tuple(sf.LegEntry(Decimal(e), CAPTURED_AT) for e in ENTRIES)
            assert all(type(e.price) is Decimal for e in loaded.saved.entries)
            stored_text = (await conn.execute(text("SELECT definition::text FROM public.strategies WHERE id = :id"),
                                              {"id": strategy_id})).scalar_one()
            assert [(leg["planned_entry"], leg["captured_at"]) for leg in json.loads(stored_text)["legs"]] == expected
        finally:
            await trans.rollback()
