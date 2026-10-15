"""W-061 / REQ-038 AC-5: Save Draft stores a strategy's definition and its activity history in PostgreSQL.

Spec basis (quoted): REQ-038 AC-5 "A strategy's definition and its activity history are saved in the database when the
user presses Save Draft, survive a restart, and load back exactly as saved; live prices are never saved inside the
strategy." AC-1 "Definition (...) and live state (...) are separate objects." AC-2 "Before the first execution,
definition changes are kept as simple activity-history entries with restore, not versions". ADR-016: no silent contract
substitution.

Real rows: tests/fixtures/kite_ws/instruments-2026-10-08-subscribed.csv (Zerodha's instrument list, 2026-10-08):
NIFTY26O1322800CE (NFO exchange token 44624), NIFTY26O1323000CE (44632), NIFTY26O1322400PE (44604),
NIFTY26O1322200PE (44595), NIFTY26O1323100CE (the edited wing), all expiry 2026-10-13, lot 65, tick 0.05.

Database tests need TEST_DATABASE_URL / TEST_ADMIN_DATABASE_URL (PostgreSQL 16 in CI); they skip locally. Every test
runs in a rolled-back transaction EXCEPT the core proof: a restart can only be proven by a second engine, which sees
only committed rows. It commits five catalogue contracts and one strategy under a fresh user_ref, and at the end
delists those contracts through the catalogue's forced admin path (the database refuses retiring a contract before its
expiry; the catalogue never deletes), so no later test sees them live. The delisted rows and one audit event remain:
a test elsewhere that counts the WHOLE catalogue table or audit chain must run before this file (it sorts last today).
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from ofo.engine.legs import Action, Instrument
from ofo.strategy import stored_form as sf
from ofo_app import strategy_store as store
from ofo_app.catalogue_store import apply_update, parse_rows_naming_the_row
from ofo_app.db import get_db
from ofo_app.main import create_app
from ofo_app.routes import strategies as strategy_routes

IST = timezone(timedelta(hours=5, minutes=30))
AS_OF = datetime(2026, 10, 8, 9, 0, tzinfo=IST)
FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "kite_ws" / "instruments-2026-10-08-subscribed.csv"
EXPIRY = date(2026, 10, 13)
LOT = 65
#: The Iron Condor in the work item's proof: (Zerodha symbol, side, instrument, strike, exchange token)
IRON_CONDOR = [("NIFTY26O1322800CE", "SELL", Instrument.CE, Decimal("22800"), 44624),
               ("NIFTY26O1323000CE", "BUY", Instrument.CE, Decimal("23000"), 44632),
               ("NIFTY26O1322400PE", "SELL", Instrument.PE, Decimal("22400"), 44604),
               ("NIFTY26O1322200PE", "BUY", Instrument.PE, Decimal("22200"), 44595)]
WING = "NIFTY26O1323100CE"
SYMBOLS = [s for s, *_ in IRON_CONDOR] + [WING]
GUARD_SQLSTATE = "OF008"
INSUFFICIENT_PRIVILEGE = "42501"
CHECK_VIOLATION = "23514"
LIVE_COLUMN_WORDS = {"ltp", "bid", "ask", "volume", "oi", "iv", "delta", "gamma", "theta", "vega", "pnl", "margin",
                     "spot", "price"}  # the brief's list; LIVE_STATE_NAMES (from the LiveState classes) is checked too
STRATEGY_COLUMNS = {"id", "user_ref", "underlying", "status", "created_at", "updated_at", "definition", "revision",
                    "definition_schema_version"}
HISTORY_COLUMNS = {"id", "strategy_id", "seq", "at", "change_summary", "definition", "definition_schema_version"}


def _user() -> str:
    return "test-" + uuid.uuid4().hex


def _fixture_rows(symbols: list[str] | None = None):
    with FIXTURE.open(encoding="utf-8", newline="") as stream:
        rows = list(parse_rows_naming_the_row(stream))  # ParsedInstruments is a list of ListedContract
    if symbols is None:
        return rows
    picked = [r for r in rows if r.ref("zerodha").broker_symbol in symbols]
    assert sorted(r.ref("zerodha").broker_symbol for r in picked) == sorted(symbols)
    return picked


async def _ids(conn) -> dict[str, int]:
    rows = (await conn.execute(text(
        "SELECT b.broker_symbol, c.id FROM public.broker_instruments b JOIN public.catalogue_contracts c "
        "ON c.id = b.contract_id WHERE b.broker = 'zerodha' AND b.broker_symbol = ANY(:s) "
        "AND NOT c.retired AND NOT c.delisted"), {"s": SYMBOLS})).all()
    return {r[0]: int(r[1]) for r in rows}


def _body(ids: dict[str, int], wing: str = "NIFTY26O1323000CE", **extra) -> dict:
    legs = [{"contract_id": ids[wing if s == "NIFTY26O1323000CE" else s], "action": side, "quantity": LOT}
            for s, side, *_ in IRON_CONDOR]
    return {"underlying": "NIFTY", "legs": legs, "rules_ref": None, "risk_limits": {}, "preferences": {}} | extra


#: ADR-064 / ADR-069: all 3 risk-limit names (decimal strings) and all 6 preference names (identifiers), literal.
FILLED_LIMITS = {"max_loss": "9000.50", "max_capital": "250000", "max_margin": "180000.25"}
FILLED_PREFS = {"objective": "income", "market_view": "neutral", "risk_preference": "low", "capital": "300000",
                "expected_range_low": "22400", "expected_range_high": "23000"}
FILLED = {"rules_ref": "rule_set_1", "risk_limits": FILLED_LIMITS, "preferences": FILLED_PREFS}


def _expected_document(ids: dict[str, int], strike_text: dict[str, str], maps: dict | None = None) -> dict:
    """The stored form, written from the fixture and the requirement (never from running the code)."""
    maps = maps or {"rules_ref": None, "risk_limits": {}, "preferences": {}}
    return {"schema_version": 1, "underlying": "NIFTY", **maps,
            "legs": [{"contract_id": ids[s], "action": side, "instrument": inst.value, "strike": strike_text[s],
                      "expiry": "2026-10-13", "quantity": 65} for s, side, inst, *_ in IRON_CONDOR]}


def _app(maker, user_ref: str):
    app = create_app()

    async def _db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[strategy_routes.current_user_ref] = lambda: user_ref
    return app


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


# ---------------------------------------------------------------------------------------------------------------
# Core proof (commits; see the module docstring)
# ---------------------------------------------------------------------------------------------------------------


async def _digests(admin_engine) -> dict[str, str]:
    """One md5 per public table over every row: equal before and after means the test left nothing behind."""
    async with admin_engine.connect() as conn:
        names = [r[0] for r in await conn.execute(text(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY 1"))]
        return {name: (await conn.execute(text(
            f"SELECT md5(coalesce(string_agg(x::text, '|' ORDER BY x::text), '')) FROM public.\"{name}\" x"
        ))).scalar_one() for name in names}


async def _remove_own_rows(admin_engine, contract_ids: list[int], user_ref: str) -> None:
    """Deletes exactly this test's rows - its strategies and their history, its contracts and every row that names
    them - in one owner transaction with the guard triggers off for that transaction only (session_replication_role
    is LOCAL; CI's admin role is the superuser that ran the migrations). Nothing else is touched (digest check)."""
    async with admin_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(text("SET LOCAL session_replication_role = replica"))
            await conn.execute(text("DELETE FROM public.strategy_history WHERE strategy_id IN "
                                    "(SELECT id FROM public.strategies WHERE user_ref = :u)"), {"u": user_ref})
            await conn.execute(text("DELETE FROM public.strategies WHERE user_ref = :u"), {"u": user_ref})
            tables = [r[0] for r in await conn.execute(text(
                "SELECT table_name FROM information_schema.columns WHERE table_schema = 'public' "
                "AND column_name = 'contract_id' ORDER BY 1"))]
            for table in tables:
                await conn.execute(text(f'DELETE FROM public."{table}" WHERE contract_id = ANY(:ids)'),
                                   {"ids": contract_ids})
            await conn.execute(text("DELETE FROM public.catalogue_contracts WHERE id = ANY(:ids)"),
                               {"ids": contract_ids})


@pytest.mark.parametrize("run", [1, 2], ids=["first-run", "second-run-same-database"])
async def test_core_proof_iron_condor_saves_and_loads_back_exactly_through_a_new_engine(app_engine, admin_engine,
                                                                                         run):
    """Runs twice on the same database: the second run would fail ``added == 5`` if the first left its rows."""
    url = os.environ["TEST_DATABASE_URL"]
    user = _user()
    before = await _digests(admin_engine)
    ids: dict[str, int] = {}
    second = None
    try:
        async with app_engine.connect() as conn:
            async with conn.begin():
                result = await apply_update(conn, _fixture_rows(SYMBOLS), as_of=AS_OF)
            ids = await _ids(conn)
            assert result.added == 5
            strike_text = dict((await conn.execute(text(
                "SELECT b.broker_symbol, c.strike::text FROM public.catalogue_contracts c JOIN public.broker_instruments b "
                "ON b.contract_id = c.id WHERE c.id = ANY(:ids)"), {"ids": list(ids.values())})).all())
        assert set(ids) == set(SYMBOLS)
        assert all(Decimal(strike_text[s]) == strike for s, _, _, strike, _ in IRON_CONDOR)
        expected = _expected_document(ids, strike_text, FILLED)
        # Save Draft
        maker = async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
        async with _client(_app(maker, user)) as ac:
            saved = await ac.post("/strategies", json=_body(ids, **FILLED))
        assert saved.status_code == 201, saved.text
        strategy_id = saved.json()["id"]
        assert saved.json()["status"] == "draft" and saved.json()["definition"] == expected
        # restart: the first engine is gone, a new one reads the row
        await app_engine.dispose()
        second = create_async_engine(url, poolclass=NullPool, connect_args={"server_settings": {"jit": "off"}})
        maker2 = async_sessionmaker(second, class_=AsyncSession, expire_on_commit=False)
        async with maker2() as session:
            loaded = await store.load(session, user, strategy_id)
        legs = loaded.saved.definition.legs
        assert [(leg.action.value, leg.instrument, leg.strike, leg.expiry, leg.quantity) for leg in legs] == [
            (side, inst, strike, EXPIRY, 65) for _, side, inst, strike, _ in IRON_CONDOR]
        assert loaded.saved.contract_ids == tuple(ids[s] for s, *_ in IRON_CONDOR)
        assert sf.to_document(loaded.saved) == expected
        assert dict(loaded.saved.definition.risk_limits) == {
            "max_loss": Decimal("9000.50"), "max_capital": Decimal("250000"), "max_margin": Decimal("180000.25")}
        assert dict(loaded.saved.definition.preferences) == FILLED_PREFS
        assert loaded.saved.definition.rules_ref == "rule_set_1"
        async with _client(_app(maker2, user)) as ac:
            got = await ac.get(f"/strategies/{strategy_id}")
            assert got.status_code == 200 and got.json()["definition"] == expected
            listed = await ac.get("/strategies")
            assert [s["id"] for s in listed.json()["strategies"]] == [strategy_id]
            # edit one strike (the bought call 23000 -> 23100) and save: one history entry, holding the original
            edited = await ac.put(f"/strategies/{strategy_id}", json=_body(ids, wing=WING, expected_revision=1, **FILLED))
            assert edited.status_code == 200, edited.text
            assert edited.json()["definition"]["legs"][1]["contract_id"] == ids[WING]
            assert edited.json()["revision"] == 2
            history = (await ac.get(f"/strategies/{strategy_id}/history")).json()["entries"]
            assert [(e["seq"], e["definition"]) for e in history] == [(1, expected)]
            assert "23000" in history[0]["change_summary"] and "23100" in history[0]["change_summary"]
            # restore entry 1: the original definition again; the edited one is kept as entry 2
            restored = await ac.post(f"/strategies/{strategy_id}/restore/1", params={"expected_revision": 2})
            assert restored.status_code == 200 and restored.json()["definition"] == expected
            assert restored.json()["revision"] == 3
            history = (await ac.get(f"/strategies/{strategy_id}/history")).json()["entries"]
            assert [e["seq"] for e in history] == [1, 2]
            assert history[0]["definition"] == expected
            assert history[1]["definition"]["legs"][1]["contract_id"] == ids[WING]
        # the strategy tables hold no live-market column
        async with second.connect() as conn:
            assert await _columns(conn) == {"strategies": STRATEGY_COLUMNS, "strategy_history": HISTORY_COLUMNS}
    finally:
        if second is not None:
            await second.dispose()
        if not ids:  # the load committed but the lookup never ran: find this test's contracts again
            async with admin_engine.connect() as conn:
                ids = await _ids(conn)
        await _remove_own_rows(admin_engine, list(ids.values()), user)
    # no other contract was delisted or touched, and nothing of this test is left (run-order independent)
    assert await _digests(admin_engine) == before, f"run {run} left rows behind"


# ---------------------------------------------------------------------------------------------------------------
# Schema: no live-market column; privileges and the guard (rolled back)
# ---------------------------------------------------------------------------------------------------------------


async def _columns(conn) -> dict[str, set[str]]:
    rows = (await conn.execute(text(
        "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'public' "
        "AND table_name IN ('strategies', 'strategy_history')"))).all()
    out: dict[str, set[str]] = {}
    for table, column in rows:
        out.setdefault(table, set()).add(column)
    return out


async def test_ac5_the_strategy_tables_have_no_live_market_column(app_engine):
    async with app_engine.connect() as conn:
        columns = await _columns(conn)
    assert columns == {"strategies": STRATEGY_COLUMNS, "strategy_history": HISTORY_COLUMNS}
    words = {w for cols in columns.values() for c in cols for w in c.split("_")} | {
        c for cols in columns.values() for c in cols}
    assert not words & (LIVE_COLUMN_WORDS | sf.LIVE_STATE_NAMES), words & (LIVE_COLUMN_WORDS | sf.LIVE_STATE_NAMES)


async def _expect_refused(conn, sql: str, sqlstate: str, params: dict | None = None) -> None:
    savepoint = await conn.begin_nested()
    with pytest.raises(DBAPIError) as err:
        await conn.execute(text(sql), params or {})
    await savepoint.rollback()
    assert getattr(err.value.orig, "sqlstate", None) == sqlstate, err.value


async def _saved_in(conn, user: str, ids: dict[str, int], wing: str = "NIFTY26O1323000CE"):
    saved = await store.build_definition(conn, "NIFTY", [
        sf.LegChoice(ids[wing if s == "NIFTY26O1323000CE" else s], Action(side), LOT) for s, side, *_ in IRON_CONDOR])
    return saved


async def _with_draft(conn, user: str):
    await apply_update(conn, _fixture_rows(), as_of=AS_OF)
    ids = await _ids(conn)
    stored = await store.save_draft(conn, user, await _saved_in(conn, user, ids))
    return ids, stored


@pytest.mark.parametrize("sql", [
    "DELETE FROM public.strategies WHERE id = :id",
    "TRUNCATE public.strategies",
    "UPDATE public.strategies SET underlying = 'SENSEX' WHERE id = :id",
    "UPDATE public.strategies SET status = 'draft' WHERE id = :id",
    "UPDATE public.strategies SET user_ref = 'someone' WHERE id = :id",
    "UPDATE public.strategy_history SET change_summary = CAST('[]' AS JSONB) WHERE strategy_id = :id",
    "DELETE FROM public.strategy_history WHERE strategy_id = :id",
    "TRUNCATE public.strategy_history",
])
async def test_ac5_the_app_role_cannot_delete_or_rewrite(app_engine, sql):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            _, stored = await _with_draft(conn, _user())
            await _expect_refused(conn, sql, INSUFFICIENT_PRIVILEGE, {"id": stored.id})
        finally:
            await trans.rollback()


@pytest.mark.parametrize("sql", [
    "DELETE FROM public.strategies WHERE id = :id",
    "DELETE FROM public.strategy_history WHERE strategy_id = :id",
    "UPDATE public.strategy_history SET change_summary = CAST('[]' AS JSONB) WHERE strategy_id = :id",
    "UPDATE public.strategies SET underlying = 'SENSEX' WHERE id = :id",
])
async def test_ac5_the_guard_refuses_even_the_owner(admin_engine, sql):
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, stored = await _with_draft(conn, _user())
            await store.update(conn, stored.user_ref, stored.id, await _saved_in(conn, stored.user_ref, ids, WING), expected_revision=1)
            await _expect_refused(conn, sql, GUARD_SQLSTATE, {"id": stored.id})
        finally:
            await trans.rollback()


async def test_ac5_the_database_refuses_a_float_where_a_decimal_string_belongs(app_engine):
    """Mutation 'store a float instead of a Decimal string': the CHECK refuses a JSON number as a strike or limit."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, stored = await _with_draft(conn, _user())
            good = (await conn.execute(text("SELECT definition::text FROM public.strategies WHERE id = :id"),
                                       {"id": stored.id})).scalar_one()
            insert = ("INSERT INTO public.strategies (user_ref, underlying, definition, definition_schema_version) "
                      "VALUES (:u, 'NIFTY', CAST(:d AS JSONB), 1)")
            strike = str(stored.saved.definition.legs[0].strike)
            for bad in (good.replace(f'"{strike}"', strike, 1),
                        good.replace('"risk_limits": {}', '"risk_limits": {"max_loss": 5000.5}')):
                assert bad != good
                await _expect_refused(conn, insert, CHECK_VIOLATION, {"u": _user(), "d": bad})
        finally:
            await trans.rollback()


async def test_ac5_the_database_refuses_an_update_without_its_history_entry(app_engine):
    """Mutation 'update without a history entry': the guard requires the newest entry to hold the replaced text."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, stored = await _with_draft(conn, _user())
            new = sf.dumps(await _saved_in(conn, stored.user_ref, ids, WING))
            await _expect_refused(conn, "UPDATE public.strategies SET definition = CAST(:d AS JSONB) WHERE id = :id",
                                  GUARD_SQLSTATE, {"d": new, "id": stored.id})
            # a history entry that is not the current definition is refused too
            await _expect_refused(
                conn, "INSERT INTO public.strategy_history (strategy_id, change_summary, definition, "
                      "definition_schema_version) VALUES (:id, CAST('[{\"kind\": \"legs_reordered\"}]' AS JSONB), "
                      "CAST(:d AS JSONB), 1)",
                GUARD_SQLSTATE, {"d": new, "id": stored.id})
        finally:
            await trans.rollback()


# ---------------------------------------------------------------------------------------------------------------
# The store: update, restore, fail closed (rolled back)
# ---------------------------------------------------------------------------------------------------------------


async def _history_rows(conn, strategy_id: int) -> list[tuple]:
    return [tuple(r) for r in (await conn.execute(text(
        "SELECT seq, change_summary::text, definition::text FROM public.strategy_history WHERE strategy_id = :id "
        "ORDER BY seq"), {"id": strategy_id})).all()]


async def test_ac5_update_writes_the_previous_definition_to_history_then_the_new_one(app_engine):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, stored = await _with_draft(conn, _user())
            assert await _history_rows(conn, stored.id) == []
            edited = await store.update(conn, stored.user_ref, stored.id, await _saved_in(conn, stored.user_ref, ids, WING), expected_revision=1)
            assert edited.saved.contract_ids[1] == ids[WING]
            (entry,) = await store.history(conn, stored.user_ref, stored.id)
            assert entry.seq == 1 and entry.saved == stored.saved
            # saving the same definition again is not a change: no entry
            await store.update(conn, stored.user_ref, stored.id, await _saved_in(conn, stored.user_ref, ids, WING), expected_revision=2)
            assert len(await _history_rows(conn, stored.id)) == 1
        finally:
            await trans.rollback()


async def test_ac5_restore_is_a_new_entry_and_never_deletes_history(app_engine):
    """Mutation 'restore that deletes later entries': every earlier entry is still there, unchanged."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, stored = await _with_draft(conn, _user())
            user = stored.user_ref
            await store.update(conn, user, stored.id, await _saved_in(conn, user, ids, WING), expected_revision=1)
            before = await _history_rows(conn, stored.id)
            restored = await store.restore(conn, user, stored.id, 1, expected_revision=2)
            assert restored.saved == stored.saved
            after = await _history_rows(conn, stored.id)
            assert after[:1] == before and [r[0] for r in after] == [1, 2]
            assert sf.render_summary(after[1][1]) == "restored entry 1"
            with pytest.raises(store.StrategyStoreError) as err:
                await store.restore(conn, user, stored.id, 9, expected_revision=3)
            assert err.value.code == store.HISTORY_NOT_FOUND
        finally:
            await trans.rollback()


async def test_ac5_an_error_inside_update_stores_nothing(app_engine, monkeypatch):
    """Fail closed: the history row is written, then the definition write fails: neither is kept."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, stored = await _with_draft(conn, _user())
            new = await _saved_in(conn, stored.user_ref, ids, WING)

            async def boom(*_a, **_k):
                raise RuntimeError("injected after the history insert")
            monkeypatch.setattr(store, "_write_definition", boom)
            with pytest.raises(RuntimeError, match="injected"):
                await store.update(conn, stored.user_ref, stored.id, new, expected_revision=1)
            assert await _history_rows(conn, stored.id) == []
            assert (await store.load(conn, stored.user_ref, stored.id)).saved == stored.saved
        finally:
            await trans.rollback()


# ---------------------------------------------------------------------------------------------------------------
# Every answer state of a load (rolled back)
# ---------------------------------------------------------------------------------------------------------------


async def _plant(conn, user: str, document: str, version: int = 1, underlying: str = "NIFTY") -> int:
    return (await conn.execute(text(
        "INSERT INTO public.strategies (user_ref, underlying, definition, definition_schema_version) "
        "VALUES (:u, :n, CAST(:d AS JSONB), :v) RETURNING id"),
        {"u": user, "n": underlying, "d": document, "v": version})).scalar_one()


async def test_ac5_every_answer_state_of_a_load(app_engine):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, stored = await _with_draft(conn, _user())
            user = stored.user_ref
            # found
            assert (await store.load(conn, user, stored.id)).saved == stored.saved
            # not found; another user's id (same answer: the row's existence is not told)
            for who, strategy_id in ((user, stored.id + 10_000_000), ("someone-else", stored.id)):
                with pytest.raises(store.StrategyStoreError) as err:
                    await store.load(conn, who, strategy_id)
                assert err.value.code == store.NOT_FOUND
            good = sf.dumps(stored.saved)
            cases = [
                (good.replace(f'"contract_id":{ids["NIFTY26O1322800CE"]}', '"contract_id":2147483000'), 1,
                 sf.CONTRACT_NOT_IN_CATALOGUE),
            ]
            for document, version, code in cases:
                assert document != good
                planted = await _plant(conn, user, document, version)
                with pytest.raises(sf.StoredFormError) as err:
                    await store.load(conn, user, planted)
                assert err.value.code == code, (code, err.value)
            # Shapes the database CHECK now refuses cannot be planted (tests_app/test_strategy_closed_shape.py proves
            # that; migration 0010 refuses an unknown schema_version too); the loader still refuses them with the same
            # codes (defence in depth, e.g. a restored backup).
            resolve = await store.catalogue_resolver(conn, stored.saved.contract_ids)
            for document, code in (
                (good.replace('"schema_version":1', '"schema_version":99'), sf.SCHEMA_VERSION_UNKNOWN),
                ('{"schema_version": 1, "underlying": "NIFTY", "legs": "not a list", "rules_ref": null, '
                 '"risk_limits": {}, "preferences": {}}', sf.MALFORMED),
                ('{"schema_version": 1, "underlying": "NIFTY"}', sf.MISSING_KEY),
                (good.replace('"preferences":{}', '"preferences":{},"ltp":"101.5"'), sf.UNKNOWN_KEY),
            ):
                assert document != good
                with pytest.raises(sf.StoredFormError) as err:
                    sf.loads(document, resolve)
                assert err.value.code == code, (code, err.value)
        finally:
            await trans.rollback()


async def test_ac5_api_answers_not_found_for_another_users_strategy(app_engine):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            _, stored = await _with_draft(conn, _user())

            class _Maker:
                """Hands the request the test's connection; commit/rollback are no-ops so the test's own
                transaction (rolled back below) stays the only one."""

                def __call__(self):
                    return self

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *exc):
                    return False

                async def execute(self, *a, **k):
                    return await conn.execute(*a, **k)

                def begin_nested(self):
                    return conn.begin_nested()

                async def commit(self):
                    return None

                async def rollback(self):
                    return None
            async with _client(_app(_Maker(), "someone-else")) as ac:
                for method, path in (("GET", f"/strategies/{stored.id}"), ("GET", f"/strategies/{stored.id}/history"),
                                     ("POST", f"/strategies/{stored.id}/restore/1?expected_revision=1")):
                    response = await ac.request(method, path)
                    assert (response.status_code, response.json()["code"]) == (404, "USER_INPUT_003"), path
        finally:
            await trans.rollback()


# ---------------------------------------------------------------------------------------------------------------
# The API refuses live-state fields (no database needed: refused before any query)
# ---------------------------------------------------------------------------------------------------------------


class _NoDb:
    async def execute(self, *a, **k):
        raise AssertionError("the request reached the database")

    async def commit(self):
        raise AssertionError("a refused request committed")

    async def rollback(self):  # the route rolls back on every refusal
        return None


def _offline_app():
    app = create_app()

    async def _db():
        yield _NoDb()

    app.dependency_overrides[get_db] = _db
    return app


BODY = {"underlying": "NIFTY", "legs": [{"contract_id": 1, "action": "SELL", "quantity": 65}], "rules_ref": None,
        "risk_limits": {}, "preferences": {}}


@pytest.mark.parametrize("body", [
    BODY | {"ltp": "101.5"},
    BODY | {"spot": "22950"},
    BODY | {"margin": "120000"},
    BODY | {"legs": [BODY["legs"][0] | {"bid": "10"}]},
    BODY | {"legs": [BODY["legs"][0] | {"iv": "0.12"}]},
    BODY | {"legs": [BODY["legs"][0] | {"strike": "22800"}]},  # terms come from the catalogue, never the body
    BODY | {"risk_limits": {"max_loss": 5000.5}},  # a float where a decimal string belongs
    BODY | {"legs": [BODY["legs"][0] | {"quantity": 65.0}]},
    BODY | {"unexpected": "x"},
])
@pytest.mark.parametrize("method, path", [("POST", "/strategies"), ("PUT", "/strategies/1")])
async def test_ac5_a_body_with_a_live_state_or_unknown_field_is_refused_not_dropped(body, method, path):
    async with _client(_offline_app()) as ac:
        response = await ac.request(method, path, json=body)
    assert response.status_code == 422, response.text
    live = [k for k in list(body) + list(body["legs"][0]) if k in sf.LIVE_STATE_NAMES]
    if live:
        assert response.json()["code"] == "USER_INPUT_002" and live[0] not in response.text  # generic, never echoed


#: ADR-064: the 12 spellings the Tier A re-review stored at 9ab20d5, plus exact-compare cases.
REVIEW_SPELLINGS = ["LTP", "Ltp", " ltp", "IV", "Spot", "last_price", "implied_vol", "spot_price", "entry_spot",
                    "underlying_spot", "mark_price", "prev_close", "Max_Loss"]


@pytest.mark.parametrize("maps", [{m: {n: "101.5"}} for m in ("risk_limits", "preferences") for n in REVIEW_SPELLINGS],
                         ids=[f"{m}-{n.strip() or 'blank'}{'-lead-space' if n != n.strip() else ''}"
                              for m in ("risk_limits", "preferences") for n in REVIEW_SPELLINGS])
@pytest.mark.parametrize("method, path, extra", [("POST", "/strategies", {}),
                                                 ("PUT", "/strategies/1", {"expected_revision": 1})])
async def test_ac5_a_live_state_name_inside_a_map_is_refused_by_the_api(maps, method, path, extra):
    """Review round 2 MAJOR: a live-market name used as a risk-limit or preference name is 422, before any query."""
    async with _client(_offline_app()) as ac:
        response = await ac.request(method, path, json=BODY | maps | extra)
    assert response.status_code == 422 and response.json()["code"] == "STRATEGY_VALIDATION_406", response.text


BEYOND_BIGINT = 2**63  # one past strategies.id's range


@pytest.mark.parametrize("method, path, body", [
    ("GET", f"/strategies/{BEYOND_BIGINT}", None),
    ("GET", f"/strategies/{BEYOND_BIGINT}/history", None),
    ("PUT", f"/strategies/{BEYOND_BIGINT}", BODY | {"expected_revision": 1}),
    ("POST", f"/strategies/{BEYOND_BIGINT}/restore/1?expected_revision=1", None),
])
async def test_ac5_an_id_beyond_the_bigint_range_is_not_found_without_a_query(method, path, body):
    async with _client(_offline_app()) as ac:
        response = await ac.request(method, path, json=body)
    assert (response.status_code, response.json()["code"]) == (404, "USER_INPUT_003")


async def test_ac5_a_change_based_on_an_old_revision_is_refused_and_writes_nothing(app_engine):
    """Two edits from the same loaded revision: the second is refused (409 revision_conflict), nothing written."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, stored = await _with_draft(conn, _user())
            assert stored.revision == 1
            first = await store.update(conn, stored.user_ref, stored.id,
                                       await _saved_in(conn, stored.user_ref, ids, WING), expected_revision=1)
            assert first.revision == 2
            history = await _history_rows(conn, stored.id)
            for call in (store.update(conn, stored.user_ref, stored.id, stored.saved, expected_revision=1),
                         store.restore(conn, stored.user_ref, stored.id, 1, expected_revision=1)):
                with pytest.raises(store.StrategyStoreError) as err:
                    await call
                assert err.value.code == store.REVISION_CONFLICT
            assert await _history_rows(conn, stored.id) == history
            assert (await store.load(conn, stored.user_ref, stored.id)).saved == first.saved
        finally:
            await trans.rollback()


async def test_ac5_filled_limits_and_preferences_round_trip_through_history_and_restore(app_engine):
    """Class: every stored definition with non-empty risk_limits / preferences. An update changing one limit and one
    preference writes exactly one entry holding the previous definition with all 9 values and rules_ref exactly; the
    summary renders from the catalogue with the typed old/new values; restore brings the filled maps back as entry 2."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture_rows(), as_of=AS_OF)
            ids = await _ids(conn)
            user = _user()
            legs = [sf.LegChoice(ids[s], Action(side), LOT) for s, side, *_ in IRON_CONDOR]
            limits = {"max_loss": Decimal("9000.50"), "max_capital": Decimal("250000"),
                      "max_margin": Decimal("180000.25")}
            first = await store.build_definition(conn, "NIFTY", legs, rules_ref="rule_set_1", risk_limits=limits,
                                                 preferences=dict(FILLED_PREFS))
            stored = await store.save_draft(conn, user, first)
            second = await store.build_definition(conn, "NIFTY", legs, rules_ref="rule_set_1",
                                                  risk_limits=limits | {"max_loss": Decimal("12000.75")},
                                                  preferences=FILLED_PREFS | {"market_view": "bullish"})
            await store.update(conn, user, stored.id, second, expected_revision=1)
            rows = await _history_rows(conn, stored.id)
            assert [r[0] for r in rows] == [1]
            (entry,) = await store.history(conn, user, stored.id)
            old_doc = sf.to_document(entry.saved)
            assert old_doc["rules_ref"] == "rule_set_1"
            assert old_doc["risk_limits"] == FILLED_LIMITS and old_doc["preferences"] == FILLED_PREFS
            assert dict(entry.saved.definition.risk_limits) == limits
            assert entry.saved == stored.saved
            assert sf.render_summary(rows[0][1]) == (
                "risk_limits max_loss: 9000.50 -> 12000.75; preferences market_view: neutral -> bullish")
            restored = await store.restore(conn, user, stored.id, 1, expected_revision=2)
            assert sf.to_document(restored.saved)["risk_limits"] == FILLED_LIMITS
            assert sf.to_document(restored.saved)["preferences"] == FILLED_PREFS
            assert restored.saved == stored.saved
            after = await _history_rows(conn, stored.id)
            assert [r[0] for r in after] == [1, 2]
            doc2 = json.loads(after[1][2])
            assert doc2["risk_limits"] == FILLED_LIMITS | {"max_loss": "12000.75"}
            assert doc2["preferences"] == FILLED_PREFS | {"market_view": "bullish"}
        finally:
            await trans.rollback()
