"""GC-SET step 2: the admin Settings API (REQ-167 AC-2, AC-3, AC-5), on the real database in a rolled-back transaction.

Spec basis: REQ-167 AC-2 (value in force, default, since, who, history; refused value with the reason; reset is a new
row), AC-3 (admin only, audit log, one guard), AC-5 (Charges from the dated table, a new rate set with its source URL);
ADR-222 (9) a change applies at the next check. One test per AC and per answer state.

Every request goes through the real app; ``get_db`` is the test's rolled-back session (the route's commit is a savepoint
release), so no ``app_settings`` or ``charge_rates`` row is ever kept (rows can never be deleted).
"""
from __future__ import annotations

import datetime
import pathlib
import sys
from decimal import Decimal
from http import HTTPStatus

import pytest
from fastapi import APIRouter, Depends
from httpx import ASGITransport, AsyncClient
from ofo_app.sql_time import IST_SQL_ZONE
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from test_settings_rate_wiring import _body, _live, replayed  # noqa: E402, F401 - the priced-route helpers

KEY = "pricing.risk_free_rate"
URL = f"/api/settings/{KEY}"
AUDIT_COUNT = text("SELECT count(*) FROM public.audit_events WHERE event_type = 'admin_change_recorded'")
SETTING_COUNT = text("SELECT count(*) FROM public.app_settings")
TWO_ROWS = 2
RATES = {"brokerage_per_order": "20", "stt_sell_rate": "0.001", "stt_exercise_rate": "0.00125",
         "transaction_rate_nse_fo": "0.0003503", "transaction_rate_bse_fo": "0.0000325", "sebi_rate": "0.000001",
         "stamp_buy_rate": "0.00003", "gst_rate": "0.18"}


class Env:
    def __init__(self, app, client, session, conn):
        self.app, self.client, self.session, self.conn = app, client, session, conn

    async def count(self, query):
        return (await self.conn.execute(query)).scalar_one()


@pytest.fixture
async def env(app_engine):
    from ofo_app import settings_store  # noqa: PLC0415
    from ofo_app.db import get_db  # noqa: PLC0415
    from ofo_app.main import create_app  # noqa: PLC0415
    from ofo_app.routes.outcome import get_settings_reader  # noqa: PLC0415

    conn = await app_engine.connect()
    trans = await conn.begin()
    session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    app = create_app()

    async def db():
        yield session

    async def read():
        return await settings_store.settings_in_force(session)

    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_settings_reader] = lambda: read
    try:
        async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False),
                               base_url="http://test") as client:
            yield Env(app, client, session, conn)
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()


def _setting(body: dict, key: str = KEY) -> dict:
    return next(s for g in body["groups"] for s in g["settings"] if s["key"] == key)


async def test_core_admin_changes_the_rate_and_the_next_priced_request_uses_it(env, replayed, monkeypatch):  # noqa: F811
    """Core: default 0.065 (no row) -> POST 0.07 now -> GET shows 0.07 with set_by and history -> POST 6.5 refused with
    "Enter 0.065 for 6.5%" -> the priced route's next request uses 0.07."""
    used = _live(replayed, monkeypatch)
    first = (await env.client.get("/api/settings")).json()
    row = _setting(first)
    assert (row["value"], row["default"], row["is_default"], row["set_by"], row["earlier_values"]) == (
        "0.065", "0.065", True, None, [])
    assert (await env.client.post("/api/strategies/outcome", json=_body(replayed))).status_code == HTTPStatus.OK
    posted = await env.client.post(URL, json={"value": "0.07", "note": "RBI move"})
    assert posted.status_code == HTTPStatus.OK, posted.text
    after = _setting((await env.client.get("/api/settings")).json())
    assert (after["value"], after["is_default"], after["set_by"]) == ("0.07", False, "owner")
    assert [(h["value"], h["state"]) for h in after["earlier_values"]] == [("0.07", "in_force")]
    refused = await env.client.post(URL, json={"value": "6.5", "note": ""})
    assert refused.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "Enter 0.065 for 6.5%" in refused.json()["reason"], refused.text
    assert (await env.client.post("/api/strategies/outcome", json=_body(replayed))).status_code == HTTPStatus.OK
    assert used == [Decimal("0.065"), Decimal("0.07")]


async def test_ac2_page_shape_groups_default_since_who_history_newest_first(env):
    body = (await env.client.get("/api/settings")).json()
    group = next(g for g in body["groups"] if g["name"] == "Pricing")
    assert KEY in [s["key"] for s in group["settings"]]
    row = _setting(body)
    assert {"label", "unit", "what_it_changes", "min", "max", "default", "value", "effective_from"} <= set(row)
    assert (row["min"], row["max"], row["unit"]) == ("0", "0.5", "fraction")
    for raw in ("0.07", "0.071"):
        assert (await env.client.post(URL, json={"value": raw, "note": ""})).status_code == HTTPStatus.OK
    earlier_values = _setting((await env.client.get("/api/settings")).json())["earlier_values"]
    assert [h["value"] for h in earlier_values] == ["0.071", "0.07"]  # newest first
    assert [h["state"] for h in earlier_values] == ["in_force", "earlier"]


async def test_state_future_row_is_scheduled_not_in_force(env):
    at = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=2)).isoformat()
    posted = await env.client.post(URL, json={"value": "0.07", "effective_from": at, "note": "later"})
    assert posted.status_code == HTTPStatus.OK, posted.text
    row = _setting((await env.client.get("/api/settings")).json())
    assert (row["value"], row["is_default"]) == ("0.065", True)
    assert [(h["value"], h["state"]) for h in row["earlier_values"]] == [("0.07", "scheduled")]


async def test_state_reset_is_a_new_row_never_a_delete(env):
    await env.client.post(URL, json={"value": "0.07", "note": ""})
    reset = await env.client.post(f"{URL}/reset", json={"note": "back"})
    assert reset.status_code == HTTPStatus.OK, reset.text
    row = reset.json()
    assert row["value"] == "0.065" and row["is_default"] is False
    assert [h["value"] for h in row["earlier_values"]] == ["0.065", "0.07"]
    assert await env.count(SETTING_COUNT) == TWO_ROWS


@pytest.mark.parametrize(("value", "words"), [
    ("51", "between 0 and 0.5"), ("abc", "must be a number"), ("6.5", "Enter 0.065 for 6.5%")])
async def test_state_refused_value_422_with_reason_and_nothing_written(env, value, words):
    resp = await env.client.post(URL, json={"value": value, "note": ""})
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY and words in resp.json()["reason"], resp.text
    assert await env.count(SETTING_COUNT) == 0


async def test_refusing_a_non_time_setting_is_a_422_with_its_reason_never_a_500(env):
    """Regression: the refusal slots once called time_of(default) for EVERY key, so 6.5 for the (non-time) risk-free
    rate crashed on 0.065 and answered 500. The time slot is now built only for a time key."""
    resp = await env.client.post(URL, json={"value": "6.5", "note": ""})
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, resp.text
    assert "Enter 0.065 for 6.5%" in resp.json()["reason"]


async def test_values_are_decimal_strings_a_json_number_is_refused(env):
    for bad in (0.07, 7, None, True):
        resp = await env.client.post(URL, json={"value": bad, "note": ""})
        assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, (bad, resp.text)
    assert await env.count(SETTING_COUNT) == 0


async def test_state_unknown_key_is_404_on_change_and_reset(env):
    for path, body in (("/api/settings/pricing.no_such", {"value": "1", "note": ""}),
                       ("/api/settings/pricing.no_such/reset", {"note": ""})):
        resp = await env.client.post(path, json=body)
        assert resp.status_code == HTTPStatus.NOT_FOUND and "no setting" in resp.json()["reason"], resp.text


async def test_state_back_dated_and_naive_times_are_refused_with_reason(env):
    past = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=5)).isoformat()
    resp = await env.client.post(URL, json={"value": "0.07", "effective_from": past, "note": ""})
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY and "now or later" in resp.json()["reason"]
    resp = await env.client.post(URL, json={"value": "0.07", "effective_from": "2099-01-01T10:00:00", "note": ""})
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY and "time zone" in resp.json()["reason"]
    same = "2099-01-01T10:00:00+05:30"
    first = await env.client.post(URL, json={"value": "0.07", "effective_from": same, "note": ""})
    assert first.status_code == HTTPStatus.OK
    resp = await env.client.post(URL, json={"value": "0.06", "effective_from": same, "note": ""})
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY and "exactly that time" in resp.json()["reason"]
    assert await env.count(SETTING_COUNT) == 1


async def test_state_note_too_long_is_refused(env):
    resp = await env.client.post(URL, json={"value": "0.07", "note": "x" * 501})
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY and "at most 500" in resp.json()["reason"]


async def test_state_store_error_fails_closed_500_and_never_a_default(env, monkeypatch):
    from ofo_app import settings_store  # noqa: PLC0415

    async def broken(*a, **k):
        raise settings_store.SettingsError("stored setting refused")

    monkeypatch.setattr(settings_store, "rows_in_force", broken)
    resp = await env.client.get("/api/settings")
    assert resp.status_code == HTTPStatus.INTERNAL_SERVER_ERROR and "0.065" not in resp.text, resp.text
    resp = await env.client.post(URL, json={"value": "0.07", "note": ""})  # the answer read-back fails: 500
    assert resp.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


async def test_ac3_every_change_is_in_the_audit_log_and_reset_too(env):
    before = await env.count(AUDIT_COUNT)
    await env.client.post(URL, json={"value": "0.07", "note": "why"})
    await env.client.post(f"{URL}/reset", json={"note": ""})
    assert await env.count(AUDIT_COUNT) == before + 2
    reason = (await env.conn.execute(text(
        "SELECT payload->>'reason' FROM public.audit_events WHERE event_type = 'admin_change_recorded' "
        "ORDER BY seq DESC OFFSET 1 LIMIT 1"))).scalar_one()
    assert KEY in reason and "0.07" in reason and "why" in reason


def _unguarded_writes(api_router: APIRouter) -> list[str]:
    """Every non-read route of ``api_router`` that does not depend on ``require_admin`` (empty = fail closed holds)."""
    from ofo_app.routes import settings as route  # noqa: PLC0415

    bad = []
    for r in api_router.routes:
        methods = getattr(r, "methods", None) or set()
        if methods <= {"GET", "HEAD", "OPTIONS"}:
            continue
        if not any(dep.call is route.require_admin for dep in r.dependant.dependencies):
            bad.append(f"{sorted(methods)} {r.path}")
    return bad


async def test_ac3_the_one_guard_decides_every_write_and_fails_closed_for_a_new_write_route(env):
    from fastapi import HTTPException  # noqa: PLC0415
    from ofo_app.routes import settings as route  # noqa: PLC0415

    assert _unguarded_writes(route.router) == []
    probe = APIRouter()
    probe.add_api_route("/x", lambda: None, methods=["POST"])
    probe.add_api_route("/y", lambda: None, methods=["DELETE"], dependencies=[Depends(route.require_admin)])
    probe.add_api_route("/z", lambda: None, methods=["GET"])
    assert _unguarded_writes(probe) == ["['POST'] /x"]  # a new write route without the guard is named

    def deny():
        raise HTTPException(status_code=403)

    env.app.dependency_overrides[route.require_admin] = deny
    before = await env.count(AUDIT_COUNT)
    for path, body in ((URL, {"value": "0.07", "note": ""}), (f"{URL}/reset", {"note": ""}),
                       ("/api/settings/charges", {**RATES, "source_url": "https://x.example/a", "note": ""})):
        assert (await env.client.post(path, json=body)).status_code == HTTPStatus.FORBIDDEN, path
    assert await env.count(SETTING_COUNT) == 0 and await env.count(AUDIT_COUNT) == before
    assert (await env.client.get("/api/settings")).status_code == HTTPStatus.OK  # reading is not guarded


async def _today(env) -> datetime.date:
    return (await env.conn.execute(text(f"SELECT (clock_timestamp() {IST_SQL_ZONE})::date"))).scalar_one()


async def test_ac5_charges_group_shows_the_set_in_force_and_adds_a_new_set_with_its_source(env):
    got = (await env.client.get("/api/settings")).json()
    assert "charges" in got  # a set (name, read_on, source_url, rates) or null when none is stored yet
    before = await env.count(AUDIT_COUNT)
    url = "https://zerodha.example/charges"
    day = (await _today(env)).isoformat()
    resp = await env.client.post("/api/settings/charges",
                                 json={**RATES, "source_url": url, "read_on": day, "note": "Oct update"})
    assert resp.status_code == HTTPStatus.OK, resp.text
    out = resp.json()
    assert (out["name"], out["read_on"], out["source_url"]) == ("Charges", day, url)
    assert out["rates"]["gst_rate"] == "0.18" and out["rates"]["brokerage_per_order"] == "20"
    assert all(isinstance(v, str) for v in out["rates"].values())
    assert await env.count(AUDIT_COUNT) == before + 1


async def test_ac5_charges_refusals_name_the_reason(env):
    today = await _today(env)
    day = today.isoformat()
    base = {**RATES, "source_url": "https://zerodha.example/c", "read_on": day, "note": ""}
    assert (await env.client.post("/api/settings/charges", json=base)).status_code == HTTPStatus.OK
    again = await env.client.post("/api/settings/charges", json=base)
    assert again.status_code == HTTPStatus.UNPROCESSABLE_ENTITY and "already has a set" in again.json()["reason"]
    older = await env.client.post("/api/settings/charges",
                                  json={**base, "read_on": (today - datetime.timedelta(days=1)).isoformat()})
    assert older.status_code == HTTPStatus.UNPROCESSABLE_ENTITY and "older" in older.json()["reason"]
    bad = await env.client.post("/api/settings/charges", json={**base, "gst_rate": "abc"})
    assert bad.status_code == HTTPStatus.UNPROCESSABLE_ENTITY and "gst_rate is not an allowed number" in bad.text
    nosrc = await env.client.post("/api/settings/charges", json={**base, "source_url": "not a web address"})
    assert nosrc.status_code == HTTPStatus.UNPROCESSABLE_ENTITY and "https://" in nosrc.json()["reason"]
    floaty = await env.client.post("/api/settings/charges", json={**base, "gst_rate": 0.18})
    assert floaty.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.parametrize(("field", "value"), [
    ("gst_rate", "5"), ("gst_rate", "-0.1"), ("stt_sell_rate", "1"), ("stt_sell_rate", "-0.001"),
    ("brokerage_per_order", "-1"), ("brokerage_per_order", "100000"), ("sebi_rate", "0.5")])
async def test_ac5_a_negative_or_absurdly_large_rate_is_refused_naming_the_field(env, field, value):
    body = {**RATES, field: value, "source_url": "https://zerodha.example/c", "note": ""}
    resp = await env.client.post("/api/settings/charges", json=body)
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY and f"{field} is not an allowed number" in resp.text
    assert await env.count(SETTING_COUNT) == 0


async def test_ac5_a_read_date_after_today_is_refused_and_does_not_block_later_sets(env):
    """A mistyped year must not be stored: the append-only table would then refuse every later set."""
    today = await _today(env)
    base = {**RATES, "source_url": "https://zerodha.example/c", "note": ""}
    far = await env.client.post("/api/settings/charges", json={**base, "read_on": "2062-01-01"})
    assert far.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "has not come yet" in far.json()["reason"] and "2062-01-01" in far.json()["reason"]
    tomorrow = (today + datetime.timedelta(days=1)).isoformat()
    assert (await env.client.post("/api/settings/charges", json={**base, "read_on": tomorrow})).status_code == 422  # noqa: PLR2004
    ok = await env.client.post("/api/settings/charges", json={**base, "read_on": today.isoformat()})
    assert ok.status_code == HTTPStatus.OK, ok.text  # today is still accepted after the refusals
