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

import pytest
from ofo.engine import Action
from ofo.instruments import eligibility as el
from ofo.instruments.models import InstrumentId
from ofo_app import catalogue_picker as picker
from ofo_app import eligibility_from_zerodha as elig
from ofo_app import pinned_clock
from ofo_app import strategy_store as store
from ofo_app.catalogue_store import apply_update
from ofo_app.routes import strategies as strategies_route
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

HTTP_OK, HTTP_CREATED, HTTP_FORBIDDEN = 200, 201, 403
SECOND_REVISION, THREE_STATEMENTS = 2, 3
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
            assert resp.status_code == HTTP_CREATED, resp.text
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
            assert resp.status_code == HTTP_OK, resp.text
            assert (await store.load(conn, stored.user_ref, stored.id)).revision == SECOND_REVISION
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


def test_a_second_copy_of_a_stored_leg_counts_as_added():
    """W-092 round 2 (review MINOR 2): legs are counted per copy. Stored = contract 7 BUY once; saved = twice ->
    the second copy is ADDED (so it is checked); the first is kept. Order and other legs do not matter."""
    buy, sell = Action.BUY, Action.SELL
    assert strategies_route._added_legs([(7, buy), (7, buy)], [(7, buy)]) == [1]
    assert strategies_route._added_legs([(9, sell), (7, buy), (7, buy), (7, buy)], [(7, buy), (9, sell)]) == [2, 3]
    assert strategies_route._added_legs([(7, buy)], [(7, buy), (7, buy)]) == []  # a removed copy adds nothing
    assert strategies_route._added_legs([(7, sell)], [(7, buy)]) == [0]  # the other side is a new leg
    assert strategies_route._added_legs([(7, buy)], []) == [0]  # a new strategy: every leg is added


async def test_two_legs_on_one_stored_contract_are_refused_before_eligibility(app_engine):
    """Today the definition itself refuses two legs on one contract (422), so the copy never reaches the save."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, stored = await _with_draft(conn, _user())
            body = _body(ids, expected_revision=1)
            body["legs"].append(dict(body["legs"][0]))
            async with _client(_on(_app(_ConnMaker(conn), stored.user_ref), LIST_DAY)) as ac:
                resp = await ac.put(f"/strategies/{stored.id}", json=body)
            assert (resp.status_code, resp.json()["code"]) == (422, "STRATEGY_VALIDATION_408"), resp.text
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
                assert edit.status_code == HTTP_OK, edit.text
            async with _client(_on(_app(maker, stored.user_ref), AFTER_EXPIRY)) as ac:
                resp = await ac.post(f"/strategies/{stored.id}/restore/1?expected_revision=2")
            assert (resp.status_code, resp.json()["code"]) == (403, "BROKER_ELIGIBILITY_103"), resp.text
            assert (await store.load(conn, stored.user_ref, stored.id)).revision == SECOND_REVISION
            async with _client(_on(_app(maker, stored.user_ref), LIST_DAY)) as ac:
                ok = await ac.post(f"/strategies/{stored.id}/restore/1?expected_revision=2")
            assert ok.status_code == HTTP_OK, ok.text  # positive control: same restore on the list's own day
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
            assert type(registry) is el.ZerodhaEligibility  # the only type the gate accepts
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
    assert len(statements) == THREE_STATEMENTS, statements  # the clock query: catalogue_picker (W-133)
    assert all(s.lstrip().upper().startswith("SELECT") for s in statements), statements


# ---- W-133 (REQ-053 AC-3, finding daily-load-misses-intraday-additions): an earlier-session list is unconfirmed --

async def _loaded_india_date(conn) -> datetime.date:
    """The India date of the latest load on the database clock (last_seen_at is stamped by clock_timestamp())."""
    return (await conn.execute(text(
        "SELECT (max(last_seen_at) AT TIME ZONE 'Asia/Kolkata')::date FROM public.broker_instruments "
        "WHERE broker = 'zerodha' AND NOT retired"))).scalar_one()


_IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
FRIDAY_LOAD = datetime.datetime(2026, 10, 23, 9, 0, tzinfo=_IST)


def _next_weekday_after(day: datetime.date) -> datetime.date:
    """The next weekday after ``day``: the first day that is a later trading session, judged at 12:00 (a Saturday or
    Sunday maps back to Friday's session, so 'one calendar day later' is not later on a Friday or a Saturday)."""
    day += datetime.timedelta(days=1)
    while day.weekday() >= WEEKEND_FIRST:
        day += datetime.timedelta(days=1)
    return day


WEEKEND_FIRST = 5  # datetime.weekday(): Saturday


def _ist(day: int, hour: int, minute: int) -> datetime.datetime:
    return datetime.datetime(2026, 10, day, hour, minute, tzinfo=_IST)


def test_ac3_a_friday_load_is_current_on_saturday_and_early_monday_but_not_monday_after_publish():
    """Core proof + attack 1: loaded Friday 09:00, current Saturday 11:00 and Monday 08:00; unconfirmed Monday 09:00."""
    assert not picker.loaded_before(FRIDAY_LOAD, _ist(24, 11, 0))
    assert not picker.loaded_before(FRIDAY_LOAD, _ist(26, 8, 0))
    assert picker.loaded_before(FRIDAY_LOAD, _ist(26, 9, 0))
    assert picker.loaded_before(None, _ist(24, 11, 0))


@pytest.mark.parametrize("load_day", [19, 20, 21, 22, 23, 24, 25])  # Mon..Sun
def test_ac3_the_next_session_day_is_a_later_session_on_every_weekday(load_day):
    """Class guard: whatever weekday the load fell on, the next weekday at 12:00 is a session after the load's."""
    day = _next_weekday_after(datetime.date(2026, 10, load_day))
    assert day.weekday() < WEEKEND_FIRST and day > datetime.date(2026, 10, load_day)
    judged = datetime.datetime.combine(day, datetime.time(12, 0), tzinfo=_IST)
    assert picker.loaded_before(_ist(load_day, 14, 0), judged)


def test_ac3_a_load_before_the_publish_time_is_unconfirmed_after_it():
    """Attack 2: loaded 08:29 on a weekday, checked 09:00 the same day -> unconfirmed; loaded 08:30 -> current."""
    assert picker.loaded_before(_ist(22, 8, 29), _ist(22, 9, 0))
    assert not picker.loaded_before(_ist(22, 8, 30), _ist(22, 9, 0))
    assert picker.session_start(_ist(22, 8, 29)) == _ist(21, 8, 30)  # before publish: the previous weekday's session


async def test_ac3_a_list_last_loaded_yesterday_answers_unconfirmed_and_stores_nothing(app_engine):
    """Attack 1: today is the day after the latest load -> the leg is unconfirmed (status None) and the save is
    refused with the unconfirmed text (not the 'unavailable' text); nothing is stored."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, user = await _seeded(conn), _user()
            next_session_day = _next_weekday_after(await _loaded_india_date(conn))
            first = ids[IRON_CONDOR[0][0]]
            assert await elig.leg_statuses(conn, [first], next_session_day) == [None]
            async with _client(_on(_app(_ConnMaker(conn), user), next_session_day)) as ac:
                resp = await ac.post("/strategies", json=_body(ids))
            assert resp.status_code == HTTP_FORBIDDEN, resp.text
            assert UNAVAILABLE not in resp.text, resp.text
            assert (await conn.execute(COUNT, {"u": user})).scalar_one() == 0
        finally:
            await trans.rollback()


async def test_ac3_a_list_loaded_earlier_today_is_current(app_engine):
    """Attack 1, positive control: today == the load's India date -> the leg has a status (the refusal is the date)."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids = await _seeded(conn)
            today = await _loaded_india_date(conn)
            assert today == await picker.database_today(conn)
            status = (await elig.leg_statuses(conn, [ids[IRON_CONDOR[0][0]]], LIST_DAY))[0]
            assert status is not None and status.tradable
        finally:
            await trans.rollback()


async def test_ac3_the_picker_offers_nothing_from_a_list_from_an_earlier_session(app_engine):
    """Same class, the other read: the picker treats a list from an earlier session as unconfirmed (nothing offered)."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _seeded(conn)
            next_session_day = _next_weekday_after(await _loaded_india_date(conn))
            assert await picker.pickable_expiries(conn, "NIFTY", LIST_DAY)  # loaded today: offered
            assert await picker.pickable_expiries(conn, "NIFTY", next_session_day) == []
            assert await picker.pickable_contracts(conn, "NIFTY", next_session_day) == []
        finally:
            await trans.rollback()


@pytest.mark.parametrize("app_env", ["production", "development", "staging", "Test", "TEST", " test", ""])
async def test_ac3_attack_4_the_pinned_date_seam_answers_nothing_outside_app_env_test(app_env, monkeypatch):
    """Attack 4 (threat model: the test date seam reachable in production): with a pin set and any APP_ENV that is not
    exactly "test", the seam refuses (PinRefused) and the clock readers raise instead of judging at the pinned date.
    No database is touched: the refusal comes before any query."""
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv(pinned_clock.ENV_NAME, LIST_DAY.isoformat())
    with pytest.raises(pinned_clock.PinRefused):
        pinned_clock.pinned_today()
    with pytest.raises(pinned_clock.PinRefused):
        await picker.database_today(object())  # a conn that would fail on any use: the pin check comes first
    with pytest.raises(pinned_clock.PinRefused):
        await elig.fresh_registry(object(), underlying="NIFTY")


def test_ac3_attack_4_the_pinned_date_seam_applies_under_app_env_test_only(monkeypatch):
    """Positive control for attack 4: the same pin under APP_ENV=test is the answer; with no pin there is none."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv(pinned_clock.ENV_NAME, LIST_DAY.isoformat())
    assert pinned_clock.pinned_today() == LIST_DAY
    monkeypatch.delenv(pinned_clock.ENV_NAME)
    assert pinned_clock.pinned_today() is None


async def test_ac3_the_pre_execution_registry_is_empty_for_a_list_from_an_earlier_session(app_engine, monkeypatch):
    """The gate's own read: no load in the current session -> empty registry, so every leg is refused as unconfirmed."""
    monkeypatch.setenv("APP_ENV", "test")
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _seeded(conn)
            monkeypatch.setenv("TEST_CATALOGUE_DATE", LIST_DAY.isoformat())
            assert len(await elig.fresh_registry(conn, underlying="NIFTY")) > 0
            next_session_day = _next_weekday_after(await _loaded_india_date(conn))
            monkeypatch.setenv("TEST_CATALOGUE_DATE", next_session_day.isoformat())
            assert len(await elig.fresh_registry(conn, underlying="NIFTY")) == 0
        finally:
            await trans.rollback()
