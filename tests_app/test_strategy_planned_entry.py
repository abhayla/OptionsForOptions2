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
from ofo.engine.legs import Action
from ofo.strategy import stored_form as sf
from ofo_app import strategy_store as store
from ofo_app.catalogue_store import apply_update
from ofo_app.db import get_db
from ofo_app.eligibility_from_zerodha import get_eligibility_today
from ofo_app.main import create_app
from ofo_app.routes import strategies as strategy_routes
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from test_strategy_store import AS_OF, IRON_CONDOR, LOT, _fixture_rows, _ids, fixture_today  # the same real rows

IST = timezone(timedelta(hours=5, minutes=30))
CAPTURED = "2026-10-15T09:20:05+05:30"
CAPTURED_AT = datetime(2026, 10, 15, 9, 20, 5, tzinfo=IST)
ENTRIES = ("44.90", "11.75", "79.05", "37.15")  # ADR-075's source line, in Iron Condor leg order
REPRICED = ("46.10", "12.05", "77.80", "36.40")
REPRICED_AT = "2026-10-15T09:41:30+05:30"
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
    app.dependency_overrides[get_eligibility_today] = lambda: fixture_today  # W-092: judged on the list's own day
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


# ---------------------------------------------------------------------------------------------------------------
# Class: every history version (update = reprice, restore)
# ---------------------------------------------------------------------------------------------------------------


async def test_ac5_a_reprice_is_a_history_entry_and_restore_brings_the_old_entries_back(app_engine):
    """AC-5 + AC-2 (ADR-068 item 1: entries change only on a reprice): a save with new entries writes one history
    entry holding the previous entries ("planned entry prices repriced"); restore of entry 1 returns those entries."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids = await _catalogue(conn)
            user = _user()
            async with _client(conn, user) as ac:
                strategy_id = (await ac.post("/strategies", json=_body(ids))).json()["id"]
                same = await ac.put(f"/strategies/{strategy_id}", json=_body(ids, expected_revision=1))
                assert same.status_code == 200 and same.json()["revision"] == 1  # same entries: not a change
                repriced = await ac.put(f"/strategies/{strategy_id}",
                                        json=_body(ids, entries=REPRICED, captured=REPRICED_AT, expected_revision=1))
                assert repriced.status_code == 200, repriced.text
                assert repriced.json()["revision"] == 2
                assert _entry_pairs(repriced.json()["definition"]) == [(e, REPRICED_AT) for e in REPRICED]
                history = (await ac.get(f"/strategies/{strategy_id}/history")).json()["entries"]
                assert [e["seq"] for e in history] == [1]
                assert _entry_pairs(history[0]["definition"]) == [(e, CAPTURED) for e in ENTRIES]
                assert history[0]["change_summary"] == "planned entry prices repriced"
                restored = await ac.post(f"/strategies/{strategy_id}/restore/1", params={"expected_revision": 2})
                assert restored.status_code == 200, restored.text
                assert _entry_pairs(restored.json()["definition"]) == [(e, CAPTURED) for e in ENTRIES]
                history = (await ac.get(f"/strategies/{strategy_id}/history")).json()["entries"]
                assert [e["seq"] for e in history] == [1, 2]
                assert _entry_pairs(history[1]["definition"]) == [(e, REPRICED_AT) for e in REPRICED]
            loaded = await store.load(conn, user, strategy_id)
            assert loaded.saved.entries == tuple(sf.LegEntry(Decimal(e), CAPTURED_AT) for e in ENTRIES)
        finally:
            await trans.rollback()


async def test_ac5_a_draft_saved_without_entries_loads_without_them_and_is_never_recaptured(app_engine):
    """ADR-075 / ADR-068 item 1: a draft with no stored entry (saved before ADR-075, or a leg with no live price) loads
    with the two keys absent; the API invents none. A later save that adds entries is a reprice."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids = await _catalogue(conn)
            user = _user()
            async with _client(conn, user) as ac:
                saved = await ac.post("/strategies", json=_body(ids, entries=(None, None, None, None)))
                assert saved.status_code == 201, saved.text
                strategy_id = saved.json()["id"]
                got = (await ac.get(f"/strategies/{strategy_id}")).json()["definition"]
                # the stored form carries exactly LEG_KEYS (REQ-038 AC-5: nothing live or derived is saved); the response
                # adds only the two token fields read from the catalogue (W-071), so any other extra key still fails
                stored_doc = sf.to_document((await store.load(conn, user, strategy_id)).saved)
                assert all(set(leg) == set(sf.LEG_KEYS) for leg in stored_doc["legs"])
                reply_keys = set(sf.LEG_KEYS) | {"contract_state", "exchange_segment", "exchange_token"}  # issue #500
                assert all(set(leg) == reply_keys for leg in got["legs"])
                assert all(leg["contract_state"] == "live" for leg in got["legs"])
                mixed = await ac.put(f"/strategies/{strategy_id}",
                                     json=_body(ids, entries=("44.90", None, "79.05", None), expected_revision=1))
                assert mixed.status_code == 200, mixed.text
                assert _entry_pairs(mixed.json()["definition"]) == [("44.90", CAPTURED), (None, None),
                                                                    ("79.05", CAPTURED), (None, None)]
            assert (await store.load(conn, user, strategy_id)).saved.entries[1] is None
        finally:
            await trans.rollback()


BAD_ENTRY_LEGS = {
    "price without time": {"planned_entry": "44.90"},
    "time without price": {"captured_at": CAPTURED},
    "price as a JSON number": {"planned_entry": 44.9, "captured_at": CAPTURED},
    "price with 3 decimals": {"planned_entry": "44.901", "captured_at": CAPTURED},
    "zero price": {"planned_entry": "0", "captured_at": CAPTURED},
    "negative price": {"planned_entry": "-44.90", "captured_at": CAPTURED},
    "exponent price": {"planned_entry": "4.49E+1", "captured_at": CAPTURED},
    "time without offset": {"planned_entry": "44.90", "captured_at": "2026-10-15T11:02:17"},
    "time not a time": {"planned_entry": "44.90", "captured_at": "yesterday"},
    "time in the future": {"planned_entry": "44.90", "captured_at": "2099-01-01T00:00:00+05:30"},
    "live price next to the pair": {"planned_entry": "44.90", "captured_at": CAPTURED, "ltp": "45.10"},
}


@pytest.mark.parametrize("extra", list(BAD_ENTRY_LEGS.values()), ids=list(BAD_ENTRY_LEGS))
async def test_ac5_a_malformed_planned_entry_is_refused_and_nothing_is_stored(app_engine, extra):
    """AC-5: a one-sided, malformed, future or live-price-carrying entry is refused with 422; no strategy row."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids = await _catalogue(conn)
            user = _user()
            body = _body(ids, entries=(None, None, None, None))
            body["legs"][0] |= extra
            async with _client(conn, user) as ac:
                response = await ac.post("/strategies", json=body)
            assert response.status_code == 422, response.text
            assert await store.list_strategies(conn, user) == []
        finally:
            await trans.rollback()


async def test_ac5_a_utc_capture_time_is_stored_canonically_and_reloads_as_the_same_instant(app_engine):
    """The planned-entry route can return "Z" times; the store keeps the canonical isoformat and the same instant."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids = await _catalogue(conn)
            user = _user()
            async with _client(conn, user) as ac:
                saved = await ac.post("/strategies", json=_body(ids, captured="2026-10-15T03:50:05Z"))
            assert saved.status_code == 201, saved.text
            loaded = await store.load(conn, user, saved.json()["id"])
            assert {e.captured_at for e in loaded.saved.entries} == {CAPTURED_AT}
            assert sf.to_document(loaded.saved)["legs"][0]["captured_at"] == "2026-10-15T03:50:05+00:00"
        finally:
            await trans.rollback()


# ---------------------------------------------------------------------------------------------------------------
# The database: the leg key set is an allow-list (finding guard-as-forbidden-list)
# ---------------------------------------------------------------------------------------------------------------


async def _stored_document(conn, ids) -> dict:
    user = _user()
    async with _client(conn, user) as ac:
        strategy_id = (await ac.post("/strategies", json=_body(ids))).json()["id"]
    text_ = (await conn.execute(text("SELECT definition::text FROM public.strategies WHERE id = :id"),
                                {"id": strategy_id})).scalar_one()
    return json.loads(text_)


def _leg_variants(good_leg: dict) -> dict[str, tuple[dict, bool]]:
    """Generated, not hand-picked: every leg key set built from the 8 allowed keys plus each live-state name and a
    stranger, and every value type in each entry slot. -> name: (leg, allowed)."""
    base = {k: v for k, v in good_leg.items() if k in sf.LEG_KEYS}
    out: dict[str, tuple[dict, bool]] = {"base six keys": (base, True), "with the pair": (good_leg, True)}
    for key in sorted(sf.ENTRY_LEG_KEYS):
        out[f"only {key}"] = (base | {key: good_leg[key]}, False)
    for name in sorted(sf.LIVE_STATE_NAMES | {"note", "source", "planned_entry_2"}):
        out[f"pair + {name}"] = (good_leg | {name: "1"}, False)
        out[f"{name} instead of the pair"] = (base | {name: "1", "captured_at": good_leg["captured_at"]}, False)
    values = {"a JSON number": 44.9, "an integer": 44, "null": None, "true": True, "an array": ["44.90"],
              "an object": {"v": "44.90"}, "empty text": "", "text": "abc"}
    for slot in sorted(sf.ENTRY_LEG_KEYS):
        for label, value in values.items():
            out[f"{slot} as {label}"] = (good_leg | {slot: value}, False)
    for label, value, ok in (("2 decimals", "44.90", True), ("1 decimal", "44.9", True), ("integer text", "45", True),
                             ("3 decimals", "44.901", False), ("zero", "0", False), ("0.00", "0.00", False),
                             ("negative", "-1", False), ("exponent", "1E+2", False), ("13 digits", "1" * 13, False),
                             ("leading zero", "044.90", False), ("space", " 44.90", False)):
        out[f"price {label}"] = (good_leg | {"planned_entry": value}, ok)
    for label, value, ok in (("IST", CAPTURED, True), ("UTC +00:00", "2026-10-15T03:50:05+00:00", True),
                             ("microseconds", "2026-10-15T11:02:17.123456+05:30", True),
                             ("zero microseconds", "2026-10-15T11:02:17.000000+05:30", False),
                             ("no offset", "2026-10-15T11:02:17", False), ("Z", "2026-10-15T03:50:05Z", False),
                             ("date only", "2026-10-15", False), ("bad month", "2026-13-15T11:02:17+05:30", False)):
        out[f"time {label}"] = (good_leg | {"captured_at": value}, ok)
    return out


async def test_ac5_the_database_allows_exactly_the_two_leg_shapes(app_engine):
    """The guard's validator is an allow-list: six keys, or six plus BOTH planned_entry and captured_at with a positive
    paise string and an offset ISO time. Every other generated shape is refused with 23514."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids = await _catalogue(conn)
            good = await _stored_document(conn, ids)
            wrong = []
            variants = _leg_variants(good["legs"][0])
            for name, (leg, allowed) in variants.items():
                doc = good | {"legs": [leg] + good["legs"][1:]}
                state = await _expect_refused(conn, INSERT, {"u": _user(), "d": json.dumps(doc)})
                if (state is None) != allowed or (state is not None and state != CHECK_VIOLATION):
                    wrong.append((name, allowed, state))
            assert wrong == []
            assert len(variants) >= 60
        finally:
            await trans.rollback()


async def test_ac5_the_database_takes_the_repriced_summary_kind_and_no_extra_key(app_engine):
    """The history summary kind ``entries_repriced`` is exactly {"kind"}; an extra key is refused (23514)."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids = await _catalogue(conn)
            user = _user()
            async with _client(conn, user) as ac:
                strategy_id = (await ac.post("/strategies", json=_body(ids))).json()["id"]
            current = (await conn.execute(text("SELECT definition::text FROM public.strategies WHERE id = :id"),
                                          {"id": strategy_id})).scalar_one()
            sql = ("INSERT INTO public.strategy_history (strategy_id, change_summary, definition, "
                   "definition_schema_version) VALUES (:id, CAST(:s AS JSONB), CAST(:d AS JSONB), 1)")
            bad = await _expect_refused(conn, sql, {"id": strategy_id, "d": current,
                                                    "s": json.dumps([{"kind": "entries_repriced", "x": 1}])})
            assert bad == CHECK_VIOLATION
            good = await _expect_refused(conn, sql, {"id": strategy_id, "d": current,
                                                     "s": json.dumps([{"kind": "entries_repriced"}])})
            assert good is None
        finally:
            await trans.rollback()


# ---------------------------------------------------------------------------------------------------------------
# Migration 0011: down and up on the real database; the downgrade refuses while an entry is stored
# ---------------------------------------------------------------------------------------------------------------


async def test_0011_downgrade_refuses_with_an_entry_then_round_trips_without_one(admin_engine):
    """Down (0010's validators): refused while a stored leg holds a planned entry; with none, the pair is refused
    after the downgrade and accepted again after the upgrade; the allowlist 'post' check passes both ways."""
    from _migration_replay import round_trip_sql
    own_down, own_up, down, up = round_trip_sql("0011_strategy_planned_entry.py")
    assert "'pre'" in own_up[0] and "'post'" in own_up[-1] and "'post'" in own_down[-1]
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids = await _catalogue(conn)
            good = await _stored_document(conn, ids)  # a row WITH entries now exists in this transaction
            savepoint = await conn.begin_nested()
            with pytest.raises(DBAPIError, match="holds a planned entry"):
                for sql in down:
                    await conn.execute(text(sql))
            await savepoint.rollback()
            await conn.execute(text("SET LOCAL session_replication_role = replica"))  # this test's rows only
            await conn.execute(text("DELETE FROM public.strategy_history WHERE strategy_id IN (SELECT id FROM "
                                    "public.strategies WHERE definition -> 'legs' -> 0 ? 'planned_entry')"))
            await conn.execute(text("DELETE FROM public.strategies WHERE definition -> 'legs' -> 0 ? 'planned_entry'"))
            await conn.execute(text("SET LOCAL session_replication_role = origin"))
            for sql in down:
                await conn.execute(text(sql))
            assert await _expect_refused(conn, INSERT, {"u": _user(), "d": json.dumps(good)}) == CHECK_VIOLATION
            for sql in up:
                await conn.execute(text(sql))
            assert await _expect_refused(conn, INSERT, {"u": _user(), "d": json.dumps(good)}) is None
        finally:
            await trans.rollback()
