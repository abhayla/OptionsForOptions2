"""W-092 / REQ-053 AC-3 (ADR-104): the builder blocks a leg Zerodha's data does not allow, at add time (Save Draft and
edit), and the app builds a FRESH registry from the store for the just-before-execution check. Real PostgreSQL only
(ADR-048); every test rolls back.

Spec basis (quoted): REQ-053 AC-3 "Before a leg is added, the builder checks what Zerodha data allows and blocks legs
that are currently unavailable; the check repeats just before execution."; AC-2 "The contract catalogue (what exists)
is stored separately from current eligibility (what Zerodha permits)"; AC-4 "The platform does not re-implement
Zerodha's RMS rules."

Real rows: the recorded 2026-10-08 Zerodha list (tests/fixtures/kite_ws/instruments-2026-10-08-subscribed.csv), the
Iron Condor of test_strategy_store (expiry 2026-10-13). The domain core proof on the 2026-10-16 list is
tests/execution/test_eligibility_from_zerodha_list.py.
"""

from __future__ import annotations

import datetime
import inspect

from ofo.instruments import eligibility as el
from ofo.instruments.models import InstrumentId
from ofo_app import eligibility_from_zerodha as elig
from ofo_app import strategy_store as store
from ofo_app.catalogue_store import apply_update
from sqlalchemy import text
from sqlalchemy.sql.elements import TextClause
from test_strategy_followups import _ConnMaker
from test_strategy_store import (
    AS_OF,
    IRON_CONDOR,
    LOT,
    WING,
    _app,
    _body,
    _client,
    _fixture_rows,
    _ids,
    _user,
    _with_draft,
)

LIST_DAY = AS_OF.date()  # 2026-10-08, the recorded list's day
AFTER_EXPIRY = datetime.date(2026, 10, 14)  # the condor's contracts expired 2026-10-13
FIRST_LEG = "Leg 1 (SELL NIFTY 22,800.00 CE, expiry 13 Oct 2026)"  # the catalogue's strike, as the gate renders it
UNAVAILABLE = "is currently unavailable on Zerodha"
COUNT = text("SELECT count(*) FROM public.strategies WHERE user_ref = :u")
LOADED_AT = text("SELECT max(last_seen_at) FROM public.broker_instruments WHERE broker = 'zerodha' AND NOT retired")


def _on(app, day: datetime.date):
    async def _today(_db) -> datetime.date:
        return day
    app.dependency_overrides[elig.get_eligibility_today] = lambda: _today
    return app


async def _seeded(conn) -> dict[str, int]:
    await apply_update(conn, _fixture_rows(), as_of=AS_OF)
    return await _ids(conn)


async def test_ac3_save_draft_refuses_an_expired_leg_with_the_gates_message_and_stores_nothing(app_engine):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, user = await _seeded(conn), _user()
            async with _client(_on(_app(_ConnMaker(conn), user), AFTER_EXPIRY)) as ac:
                resp = await ac.post("/strategies", json=_body(ids))
            assert (resp.status_code, resp.json()["code"]) == (403, "BROKER_ELIGIBILITY_103"), resp.text
            assert FIRST_LEG in resp.text and UNAVAILABLE in resp.text, resp.text
            assert (await conn.execute(COUNT, {"u": user})).scalar_one() == 0
        finally:
            await trans.rollback()


async def test_ac3_save_draft_accepts_the_same_legs_on_the_lists_own_day(app_engine):
    """Positive control: the same body on 2026-10-08 is saved (so the refusal above is the date, nothing else)."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, user = await _seeded(conn), _user()
            async with _client(_on(_app(_ConnMaker(conn), user), LIST_DAY)) as ac:
                resp = await ac.post("/strategies", json=_body(ids))
            assert resp.status_code == 201, resp.text
            assert (await conn.execute(COUNT, {"u": user})).scalar_one() == 1
        finally:
            await trans.rollback()


async def test_ac3_a_contract_the_latest_list_does_not_carry_is_refused_at_save(app_engine):
    """ADR-104 (a): listed in the latest load is required; the save path's liveness check alone would accept it."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, user = await _seeded(conn), _user()
            first = ids[IRON_CONDOR[0][0]]
            await conn.execute(text("UPDATE public.catalogue_contracts SET currently_listed = FALSE WHERE id = :id"),
                               {"id": first})
            async with _client(_on(_app(_ConnMaker(conn), user), LIST_DAY)) as ac:
                resp = await ac.post("/strategies", json=_body(ids))
            assert (resp.status_code, resp.json()["code"]) == (403, "BROKER_ELIGIBILITY_103"), resp.text
            assert FIRST_LEG in resp.text
            assert (await elig.leg_statuses(conn, [first], LIST_DAY))[0].reason == el.REASON_NOT_IN_LIST
        finally:
            await trans.rollback()


async def test_ac3_an_edit_that_keeps_an_already_stored_expired_leg_saves(app_engine):
    """(a) Old drafts stay editable: the stored legs have since expired, an unrelated change (quantity) still saves."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, stored = await _with_draft(conn, _user())
            body = _body(ids, expected_revision=1)
            for leg in body["legs"]:
                leg["quantity"] = LOT * 2
            async with _client(_on(_app(_ConnMaker(conn), stored.user_ref), AFTER_EXPIRY)) as ac:
                resp = await ac.put(f"/strategies/{stored.id}", json=body)
            assert resp.status_code == 200, resp.text
            assert (await store.load(conn, stored.user_ref, stored.id)).revision == 2
        finally:
            await trans.rollback()


async def test_ac3_an_edit_that_adds_an_expired_leg_is_refused_and_the_revision_stays(app_engine):
    """(b) A leg new relative to the stored version is checked: refused with the gate's text."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, stored = await _with_draft(conn, _user())
            async with _client(_on(_app(_ConnMaker(conn), stored.user_ref), AFTER_EXPIRY)) as ac:
                resp = await ac.put(f"/strategies/{stored.id}", json=_body(ids, wing=WING, expected_revision=1))
            assert (resp.status_code, resp.json()["code"]) == (403, "BROKER_ELIGIBILITY_103"), resp.text
            assert UNAVAILABLE in resp.text, resp.text
            assert (await store.load(conn, stored.user_ref, stored.id)).revision == 1
        finally:
            await trans.rollback()


async def test_ac3_an_edit_that_adds_an_unlisted_leg_is_refused(app_engine):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, stored = await _with_draft(conn, _user())
            await conn.execute(text("UPDATE public.catalogue_contracts SET currently_listed = FALSE WHERE id = :id"),
                               {"id": ids[WING]})
            async with _client(_on(_app(_ConnMaker(conn), stored.user_ref), LIST_DAY)) as ac:
                resp = await ac.put(f"/strategies/{stored.id}", json=_body(ids, wing=WING, expected_revision=1))
            assert (resp.status_code, resp.json()["code"]) == (403, "BROKER_ELIGIBILITY_103"), resp.text
        finally:
            await trans.rollback()


async def test_ac3_a_restore_that_brings_back_an_expired_leg_is_refused(app_engine):
    """(c) Restoring entry 1 re-adds the leg the edit swapped out; it is new relative to the current version."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, stored = await _with_draft(conn, _user())
            maker = _ConnMaker(conn)
            async with _client(_on(_app(maker, stored.user_ref), LIST_DAY)) as ac:
                edit = await ac.put(f"/strategies/{stored.id}", json=_body(ids, wing=WING, expected_revision=1))
                assert edit.status_code == 200, edit.text
            async with _client(_on(_app(maker, stored.user_ref), AFTER_EXPIRY)) as ac:
                resp = await ac.post(f"/strategies/{stored.id}/restore/1?expected_revision=2")
            assert (resp.status_code, resp.json()["code"]) == (403, "BROKER_ELIGIBILITY_103"), resp.text
            assert (await store.load(conn, stored.user_ref, stored.id)).revision == 2
            async with _client(_on(_app(maker, stored.user_ref), LIST_DAY)) as ac:
                ok = await ac.post(f"/strategies/{stored.id}/restore/1?expected_revision=2")
            assert ok.status_code == 200, ok.text  # positive control: same restore on the list's own day
        finally:
            await trans.rollback()


async def test_ac3_fresh_registry_reads_the_store_on_the_database_clock(app_engine, monkeypatch):
    """Just before execution: a NEW registry from the store; checked_at = the latest load's time; the margin reply's
    refusal narrows a leg with Zerodha's text. "Today" comes only from the database clock's seam (the test-only pin)."""
    monkeypatch.setenv("APP_ENV", "test")
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _seeded(conn)
            row = (await conn.execute(text(
                "SELECT c.exchange_segment, c.exchange_token FROM public.catalogue_contracts c JOIN "
                "public.broker_instruments b ON b.contract_id = c.id WHERE b.broker_symbol = :s AND NOT c.retired "
                "AND NOT c.delisted"), {"s": IRON_CONDOR[0][0]})).one()
            first = InstrumentId(row[0], int(row[1]))
            loaded_at = (await conn.execute(LOADED_AT)).scalar_one()

            monkeypatch.setenv("TEST_CATALOGUE_DATE", LIST_DAY.isoformat())
            registry = await elig.fresh_registry(conn, underlying="NIFTY")
            assert (registry.get(first).tradable, registry.get(first).checked_at) == (True, loaded_at)

            refused = await elig.fresh_registry(conn, underlying="NIFTY", margin_refusals={first: "Zerodha text"})
            assert (refused.get(first).tradable, refused.get(first).reason) == (False, "Zerodha text")

            monkeypatch.setenv("TEST_CATALOGUE_DATE", AFTER_EXPIRY.isoformat())
            later = await elig.fresh_registry(conn, underlying="NIFTY")
            assert (later.get(first).tradable, later.get(first).reason) == (False, el.REASON_EXPIRED)
        finally:
            await trans.rollback()


def test_fresh_registry_takes_no_verdict_from_its_caller():
    """Finding caller-supplied-verdict-trusted: no registry, status or 'today' parameter; refusals only narrow."""
    params = set(inspect.signature(elig.fresh_registry).parameters)
    assert params == {"conn", "underlying", "margin_refusals"}, params
    assert set(inspect.signature(elig.leg_statuses).parameters) == {"conn", "contract_ids", "today"}


def test_the_eligibility_reader_never_writes():
    """AC-2: every statement in the module is a SELECT; nothing writes the catalogue or stores eligibility."""
    statements = [v.text for v in vars(elig).values() if isinstance(v, TextClause)]
    assert len(statements) == 4, statements
    assert all(s.lstrip().upper().startswith("SELECT") for s in statements), statements
