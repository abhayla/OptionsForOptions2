"""REQ-170 Q-AD-2: a user's alert-style pin per strategy (migration 0035, ``ofo_app.strategy_alert_style_store``).

Spec basis: REQ-170 Q-AD-2 "the style is taken from the strategy and changes by itself as expiry nears ... the user
may pin a style per strategy"; REQ-168 AC-3 "every read and write is keyed by the user".

Real input: a saved strategy from the recorded instrument fixture (``test_strategy_store._with_draft``). Every store
test runs in a rolled-back transaction: the pin table is insert-only, a committed row would stay for ever.
"""
from __future__ import annotations

import datetime
import importlib.util
import pathlib
from types import SimpleNamespace

import pytest
from _migration_replay import round_trip_sql
from httpx import ASGITransport, AsyncClient
from ofo.adjustment import alert_presets
from ofo.errors.explanations import render_explanation
from ofo.timeutil import IST
from ofo_app import db as app_db
from ofo_app import settings_store
from ofo_app import strategy_alert_style_store as store
from ofo_app import strategy_store as store_strategies
from ofo_app.catalogue_store import apply_update
from ofo_app.routes import alert_style as route
from ofo_app.routes.adjustment import get_market_reader, get_tracked_reader
from ofo_app.routes.broker import current_user_ref
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_adjustment_plan import _reset_engine, _seeded
from test_strategy_store import _MAX_DELIST, AS_OF, _fixture_rows, _ids, _saved_in, _user, _with_draft

ROOT = pathlib.Path(__file__).resolve().parent.parent
TABLE = "public.strategy_alert_style"


def _migration():
    path = ROOT / "backend" / "ofo_app" / "alembic" / "versions" / "0035_strategy_alert_style.py"
    found = importlib.util.spec_from_file_location("ofo_migration_0035_test", path)
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)
    return module


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _strategy(db) -> tuple[str, int]:
    user = _user()
    _, stored = await _with_draft(db, user)
    return user, stored.id


# ---- the core proof ---------------------------------------------------------------------------------------------

async def test_core_proof_pin_monthly_then_back_to_automatic(db):
    user, sid = await _strategy(db)
    assert await store.pin_of(db, user, sid) == store.StoredPin(None, None)  # absent: automatic
    pinned = await store.set_pin(db, user, sid, "monthly")
    assert pinned.style == "monthly"
    got = await store.pin_of(db, user, sid)
    assert (got.style, got.effective_from) == ("monthly", pinned.effective_from)
    auto = await store.set_pin(db, user, sid, None)
    got = await store.pin_of(db, user, sid)
    assert (got.style, got.effective_from) == (None, auto.effective_from)
    rows = (await db.execute(text(f"SELECT style FROM {TABLE} WHERE user_ref = :u ORDER BY effective_from"),  # noqa: S608
                             {"u": user})).scalars().all()
    assert rows == ["monthly", None]  # history kept: the return to automatic is a row, never a delete


@pytest.mark.parametrize("sql", [
    f"UPDATE {TABLE} SET style = 'weekly'",  # noqa: S608 - constant table name
    f"DELETE FROM {TABLE}",  # noqa: S608 - constant table name
    f"TRUNCATE {TABLE}",
])
async def test_the_application_role_cannot_update_delete_or_truncate(db, sql):
    user, sid = await _strategy(db)
    await store.set_pin(db, user, sid, "weekly")
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(text(sql))


@pytest.mark.parametrize("sql", [
    f"UPDATE {TABLE} SET style = 'weekly'",  # noqa: S608 - constant table name
    f"DELETE FROM {TABLE}",  # noqa: S608 - constant table name
    f"TRUNCATE {TABLE}",
])
async def test_the_guard_refuses_update_delete_truncate_even_for_the_owner(admin_engine, sql):
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user, sid = await _strategy(conn)
            await store.set_pin(conn, user, sid, "monthly")
            with pytest.raises(DBAPIError) as info:
                await conn.execute(text(sql))
            assert getattr(info.value.orig, "sqlstate", None) == "OF035"
        finally:
            await trans.rollback()


async def test_a_back_dated_raw_insert_is_refused(db):
    user, sid = await _strategy(db)
    with pytest.raises(DBAPIError) as info:
        async with db.begin_nested():
            await db.execute(text(f"INSERT INTO {TABLE} (user_ref, strategy_id, style, effective_from) "  # noqa: S608
                                  "VALUES (:u, :s, 'weekly', clock_timestamp() - interval '1 minute')"),
                             {"u": user, "s": sid})
    assert getattr(info.value.orig, "sqlstate", None) == "OF035"


async def test_a_style_outside_the_list_is_refused_by_the_store_and_the_table(db):
    user, sid = await _strategy(db)
    with pytest.raises(store.AlertStyleError):
        await store.set_pin(db, user, sid, "yearly")
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(text(f"INSERT INTO {TABLE} (user_ref, strategy_id, style, effective_from) "  # noqa: S608
                                  "VALUES (:u, :s, 'yearly', clock_timestamp())"), {"u": user, "s": sid})
    assert (await store.pin_of(db, user, sid)).style is None


async def test_another_users_strategy_is_not_found_on_read_and_write(db):
    owner, sid = await _strategy(db)
    await store.set_pin(db, owner, sid, "intraday")
    other = _user()
    with pytest.raises(store.StyleNotFound):
        await store.pin_of(db, other, sid)
    with pytest.raises(store.StyleNotFound):
        await store.set_pin(db, other, sid, "weekly")
    with pytest.raises(store.StyleNotFound):
        await store.pin_of(db, owner, 987654321)
    assert (await store.pin_of(db, owner, sid)).style == "intraday"


async def test_a_read_without_a_user_fails_closed(db):
    _, sid = await _strategy(db)
    with pytest.raises(store.AlertStyleError):
        await store.pin_of(db, "  ", sid)


def test_the_table_styles_equal_the_resolver_styles():
    assert _migration().STYLES == alert_presets.STYLES


def test_the_allowlist_chain_gains_exactly_block_27():
    m = _migration()
    previous = m.previous_allowlist_sql()
    extended = m.extended_allowlist_sql()
    assert m.ALLOWLIST_BLOCK_MARKER not in previous and extended.count(m.ALLOWLIST_BLOCK_MARKER) == 1
    assert extended.replace(m._block(), "", 1) == previous


async def test_the_post_allowlist_check_passes_on_the_migrated_database(admin_engine):
    async with admin_engine.connect() as conn:
        await conn.execute(text("SELECT public.ofo_assert_app_role_allowlist('ofo_app', 'post')"))


# ---- the route (GET / PUT /api/strategies/{id}/alert-style) on the ADJ-02 scenario ------------------------------
# ADJ-02: a weekly NIFTY iron condor, clock 2026-11-06 11:40 IST, expiry 2026-11-09 (3 days): automatic = weekly.

OK, NOT_FOUND, UNPROCESSABLE, CONFLICT = 200, 404, 422, 409
WEEKLY_AUTO = "Automatic (now Weekly)"
CHOICES = [[None, WEEKLY_AUTO], ["intraday", "Intraday"], ["weekly", "Weekly"], ["monthly", "Monthly"]]


async def _call(method: str, path: str, user: str | None = None, overrides: dict | None = None,
                **kw) -> tuple[int, dict]:
    from ofo_app.main import create_app  # noqa: PLC0415 - the env must be set first
    _reset_engine()
    app = create_app()
    if user is not None:
        app.dependency_overrides[current_user_ref] = lambda: user
    app.dependency_overrides.update(overrides or {})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.request(method, path, **kw)
    await app_db.close_db()
    return r.status_code, r.json()


@pytest.fixture
async def app_db_url(app_engine, monkeypatch):
    """The app's own engine on the fresh database (test_adjustment_plan's harness)."""
    monkeypatch.setenv("DATABASE_URL", app_engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("APP_ENV", "test")
    _reset_engine()
    yield app_engine
    await app_db.close_db()
    _reset_engine()


def _path(sid: int) -> str:
    return f"/api/strategies/{sid}/alert-style"


def _shape(body: dict) -> tuple:
    return (body["pinned"], body["automatic"], body["in_force"], body["reason_text"],
            [[c["value"], c["label"]] for c in body["choices"]])


async def test_route_core_automatic_then_pin_monthly_then_automatic_again(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    status, body = await _call("GET", _path(sid))
    assert status == OK, body
    assert body["label"] == "Alert style"
    assert _shape(body) == (None, "weekly", "weekly", None, CHOICES)
    status, body = await _call("PUT", _path(sid), json={"style": "monthly"})
    assert status == OK, body
    assert _shape(body) == ("monthly", "weekly", "monthly", None, CHOICES)
    assert _shape((await _call("GET", _path(sid)))[1]) == ("monthly", "weekly", "monthly", None, CHOICES)
    status, body = await _call("PUT", _path(sid), json={"style": None})
    assert status == OK, body
    assert _shape(body) == (None, "weekly", "weekly", None, CHOICES)


async def test_route_refuses_a_style_outside_the_list_and_writes_nothing(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    before = (await _call("GET", _path(sid)))[1]
    status, body = await _call("PUT", _path(sid), json={"style": "yearly"})
    assert (status, body) == (UNPROCESSABLE, {"reason": "That is not an alert style. Pick Automatic, Intraday, "
                                                        "Weekly or Monthly."})
    assert (await _call("GET", _path(sid)))[1] == before


async def test_route_another_users_or_a_missing_strategy_is_not_found(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    before = (await _call("GET", _path(sid)))[1]
    for method, kw in (("GET", {}), ("PUT", {"json": {"style": "intraday"}})):
        assert (await _call(method, _path(sid), user="someone-else", **kw))[0] == NOT_FOUND, method
        assert (await _call(method, _path(987654321), **kw))[0] == NOT_FOUND, method
    assert (await _call("GET", _path(sid)))[1] == before


# ---- automatic_style's refusals (no guessed style), on fake readers -----------------------------------------------

def _tracked(*expiries: datetime.date):
    legs = tuple(SimpleNamespace(expiry=e) for e in expiries)
    return SimpleNamespace(position=SimpleNamespace(legs=legs))


def _market(kind: str | None, now: datetime.datetime):
    return SimpleNamespace(expiry_kind=kind, now=now)


NOW = datetime.datetime(2026, 11, 6, 11, 40, tzinfo=IST)


@pytest.mark.parametrize(("expiries", "kind", "want"), [
    ((datetime.date(2026, 11, 9),), "weekly", ("weekly", None)),
    ((datetime.date(2026, 11, 7),), "weekly", ("intraday", None)),  # 1 day to expiry: intraday rules
    ((datetime.date(2026, 11, 26),), "monthly", ("monthly", None)),
    ((datetime.date(2026, 11, 9), datetime.date(2026, 11, 26)), "weekly", (None, route.SEVERAL)),
    ((datetime.date(2026, 11, 9),), None, (None, route.UNKNOWN)),  # kind not read
    ((datetime.date(2026, 11, 9),), "quarterly", (None, route.UNKNOWN)),
    ((datetime.date(2026, 11, 5),), "weekly", (None, route.UNKNOWN)),  # expiry already past
])
async def test_automatic_style_answers_or_names_why_not(expiries, kind, want):
    async def tracked_reader(_sid, _rates):
        return _tracked(*expiries)

    async def market_reader(_tracked, _ctx):
        return _market(kind, NOW)
    assert await route.automatic_style(1, tracked_reader, market_reader, None) == want


async def test_automatic_style_on_a_failed_market_read_or_no_open_leg_is_unknown():
    from ofo_app.adjustment_readers import TrackedExited  # noqa: PLC0415

    async def tracked_ok(_sid, _rates):
        return _tracked(datetime.date(2026, 11, 9))

    async def market_fails(_tracked, _ctx):
        raise ValueError("chain refused")

    async def exited(_sid, _rates):
        raise TrackedExited("no open option leg")
    assert await route.automatic_style(1, tracked_ok, market_fails, None) == (None, route.UNKNOWN)
    assert await route.automatic_style(1, exited, market_fails, None) == (None, route.UNKNOWN)


def test_the_refusal_texts_read_as_the_catalogue_says():
    assert render_explanation(route.SEVERAL) == ("This strategy has legs on more than one expiry, so its alert style "
                                                 "cannot be picked by itself. Pin a style.")
    assert render_explanation(route.UNKNOWN) == ("This strategy's expiry type or days to expiry could not be read, so "
                                                 "its alert style cannot be picked by itself. Pin a style.")


# ---- GC-ALERT1 round 2: a saved draft with no paper order (the review's MUST), refusals before the write ----------

UNKNOWN_TEXT = ("This strategy's expiry type or days to expiry could not be read, so its alert style cannot be "
                "picked by itself. Pin a style.")
SEVERAL_TEXT = ("This strategy has legs on more than one expiry, so its alert style cannot be picked by itself. "
                "Pin a style.")
UNKNOWN_CHOICES = [[None, "Automatic (not known yet)"], ["intraday", "Intraday"], ["weekly", "Weekly"],
                   ["monthly", "Monthly"]]
D1, D2 = datetime.date(2026, 11, 9), datetime.date(2026, 11, 26)


async def _draft_in(conn, user: str) -> int:
    """A saved draft with NO paper order on ``conn``; the force update copes with rows an earlier test committed."""
    await apply_update(conn, _fixture_rows(), as_of=AS_OF, max_delist_percent=_MAX_DELIST, force=True,
                       reason="test: the draft fixture contracts", actor="test")
    return (await store_strategies.save_draft(conn, user, await _saved_in(conn, user, await _ids(conn)))).id


async def _committed_draft(app_engine) -> tuple[str, int]:
    """The same, committed (the route opens its own connection); the database is throwaway."""
    user = _user()
    async with app_engine.begin() as conn:
        return user, await _draft_in(conn, user)


async def _rows(app_engine, user: str) -> list:
    async with app_engine.connect() as conn:
        found = await conn.execute(text(f"SELECT style FROM {TABLE} WHERE user_ref = :u ORDER BY effective_from"),  # noqa: S608
                                   {"u": user})
        return list(found.scalars().all())


def _readers(kind: str):
    """(overrides, why) for each way the position cannot be told; ``no orders`` keeps the real reader."""
    from ofo_app.adjustment_readers import TrackedExited  # noqa: PLC0415

    async def exited(_sid, _rates):
        raise TrackedExited("no open option leg")

    async def several(_sid, _rates):
        return _tracked(D1, D2)

    async def one(_sid, _rates):
        return _tracked(D1)

    async def kind_unknown(_tracked_, _ctx):
        return _market(None, NOW)
    return {
        "no orders": ({}, UNKNOWN_TEXT),
        "all legs exited": ({get_tracked_reader: lambda: exited}, UNKNOWN_TEXT),
        "several expiries": ({get_tracked_reader: lambda: several}, SEVERAL_TEXT),
        "unknown expiry kind": ({get_tracked_reader: lambda: one, get_market_reader: lambda: kind_unknown},
                                UNKNOWN_TEXT),
    }[kind]


@pytest.mark.parametrize("kind", ["no orders", "all legs exited", "several expiries", "unknown expiry kind"])
async def test_route_a_strategy_whose_position_cannot_be_told_answers_200_and_one_row_per_put(app_db_url, kind):
    user, sid = await _committed_draft(app_db_url)
    overrides, why = _readers(kind)
    status, body = await _call("GET", _path(sid), user=user, overrides=overrides)
    assert status == OK, body
    assert _shape(body) == (None, None, None, why, UNKNOWN_CHOICES)
    status, body = await _call("PUT", _path(sid), user=user, overrides=overrides, json={"style": "monthly"})
    assert status == OK, body
    assert _shape(body) == ("monthly", None, "monthly", why, UNKNOWN_CHOICES)
    assert await _rows(app_db_url, user) == ["monthly"]  # exactly one stored row
    status, body = await _call("PUT", _path(sid), user=user, overrides=overrides, json={"style": None})
    assert status == OK and body["pinned"] is None and body["in_force"] is None
    assert await _rows(app_db_url, user) == ["monthly", None]


async def test_route_a_refused_put_stores_nothing(app_db_url):
    user, sid = await _committed_draft(app_db_url)
    assert (await _call("PUT", _path(sid), user=user, json={"style": "yearly"}))[0] == UNPROCESSABLE
    assert (await _call("PUT", _path(sid), user="someone-else", json={"style": "weekly"}))[0] == NOT_FOUND
    assert await _rows(app_db_url, user) == [] and await _rows(app_db_url, "someone-else") == []


async def test_route_a_stored_style_that_is_no_longer_valid_is_a_catalogue_refusal_not_a_500(app_db_url, monkeypatch):
    user, sid = await _committed_draft(app_db_url)

    async def retired(*_a, **_k):
        raise store.AlertStyleError("not a trading style: 'yearly'")
    monkeypatch.setattr(store, "pin_of", retired)
    status, body = await _call("GET", _path(sid), user=user)
    assert status == UNPROCESSABLE, body
    assert body == {"reason": render_explanation("alert_style_refused_unknown")}  # fail closed, never "automatic"


async def test_route_two_puts_at_the_same_instant_second_gets_409_and_the_first_is_stored(app_db_url, monkeypatch):
    user, sid = await _committed_draft(app_db_url)
    async with app_db_url.connect() as conn:
        now = await settings_store.database_now(conn) + datetime.timedelta(minutes=1)  # not back-dated (5 s grace)

    async def fixed(_session):
        return now
    monkeypatch.setattr(settings_store, "database_now", fixed)
    assert (await _call("PUT", _path(sid), user=user, json={"style": "weekly"}))[0] == OK
    status, body = await _call("PUT", _path(sid), user=user, json={"style": "monthly"})
    assert status == CONFLICT and body["reason"] == render_explanation("settings_refused_same_time")
    assert await _rows(app_db_url, user) == ["weekly"]


async def test_the_post_allowlist_check_fails_when_the_app_role_may_update_style(admin_engine, app_engine):
    role = app_engine.url.username
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text(f'GRANT UPDATE (style) ON {TABLE} TO "{role}"'))
            with pytest.raises(DBAPIError, match=r"strategy_alert_style"):
                async with conn.begin_nested():
                    await conn.execute(text(f"SELECT public.ofo_assert_app_role_allowlist('{role}', 'post')"))
        finally:
            await trans.rollback()


async def test_downgrade_is_refused_while_rows_exist(admin_engine):
    own_down, _, _, _ = round_trip_sql("0035_strategy_alert_style.py")
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user = _user()
            sid = await _draft_in(conn, user)
            await store.set_pin(conn, user, sid, "weekly")
            with pytest.raises(DBAPIError, match=r"stored alert-style rows"):
                async with conn.begin_nested():
                    await conn.execute(text(own_down[0]))
        finally:
            await trans.rollback()
