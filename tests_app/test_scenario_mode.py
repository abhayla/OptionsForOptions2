"""GC-ADJ1 step 1b (W-196): scenario mode serves an adjustment-library scenario through the real Kite parsers, only
under APP_ENV development/test, and refuses every order route."""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from ofo_app import scenario_mode
from ofo_app.config import Settings
from ofo_app.kite_margin import KiteMargin, KiteMarginError
from ofo_app.main import create_app
from ofo_app.scenario_mode import ScenarioRefused

OK, CONFLICT, GATEWAY_TIMEOUT = 200, 409, 504
DB = "postgresql+asyncpg://example@127.0.0.1:5432/x"
REFUSED_ENVS = ["production", "staging", "", "Development ", "TEST", "dev"]


# ---- start-up refusal ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("env", REFUSED_ENVS)
def test_settings_refuse_scenario_outside_dev_and_test(env):
    with pytest.raises(ValueError, match="development/test-only"):
        Settings(DATABASE_URL=DB, APP_ENV=env, OFO_SCENARIO="ADJ-02", _env_file=None)


@pytest.mark.parametrize("env", ["development", "test"])
def test_settings_accept_scenario_in_dev_and_test(env):
    assert Settings(DATABASE_URL=DB, APP_ENV=env, OFO_SCENARIO="ADJ-02", _env_file=None).OFO_SCENARIO == "ADJ-02"


def test_settings_blank_scenario_is_not_set_in_production():
    assert Settings(DATABASE_URL=DB, APP_ENV="production", OFO_SCENARIO="  ", _env_file=None)


@pytest.mark.parametrize("env", REFUSED_ENVS)
def test_create_app_refuses_scenario_outside_dev_and_test(monkeypatch, env):
    monkeypatch.setenv("OFO_SCENARIO", "ADJ-02")
    monkeypatch.setenv("APP_ENV", env)
    with pytest.raises(ScenarioRefused):
        create_app()


def test_create_app_refuses_when_app_env_unset(monkeypatch):
    monkeypatch.setenv("OFO_SCENARIO", "ADJ-02")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setattr("ofo_app.main.app_env", lambda: None)
    with pytest.raises(ScenarioRefused):
        create_app()


def test_production_with_empty_scenario_starts(monkeypatch):
    monkeypatch.setenv("OFO_SCENARIO", "")
    monkeypatch.setenv("APP_ENV", "production")
    assert create_app() is not None


@pytest.mark.parametrize("bad", ["../../etc/passwd", "ADJ-02.json", "ADJ-2", "ADJ-02z", "adj-02", "ADJ-99"])
def test_bad_or_unknown_id_refused_without_reading_outside(bad):
    with pytest.raises(ScenarioRefused):
        scenario_mode.scenario_path(bad)


# ---- the market through the real parsers -----------------------------------------------------------------------------
def _app(monkeypatch, sid: str):
    monkeypatch.setenv("OFO_SCENARIO", sid)
    monkeypatch.setenv("APP_ENV", "test")
    return create_app()


async def _get(app, url: str):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        return await ac.get(url)


async def test_adj02_chain_spot_and_clock_served(monkeypatch):
    app = _app(monkeypatch, "ADJ-02")
    out = (await _get(app, "/api/market/chain?underlying=NIFTY&expiry=2026-11-09&strikes_each_side=2")).json()
    assert out["state"] == "LIVE" and out["spot"] == "23420.00" and out["atm_strike"] == "23400.00"
    assert out["spot_at"] == "2026-11-06T11:39:59+05:30"  # clock 11:40, data age 1 s
    row = next(r for r in out["rows"] if r["strike"] == "23400.00")
    scn = scenario_mode.load("ADJ-02")
    fixture = {(r["strike"], r["type"]): r for r in scn.data["market"]["chains"][0]["rows"]}
    assert row["ce"]["ltp"] == f"{Decimal(fixture[('23400', 'CE')]['ltp']):.2f}"
    assert row["pe"]["bid"] == f"{Decimal(fixture[('23400', 'PE')]['bid']):.2f}"
    idx = (await _get(app, "/api/market/indices")).json()
    assert idx["answered_at"] == "2026-11-06T11:40:00+05:30"
    assert idx["indices"][0]["value"] == "23420.00"
    feats = (await _get(app, "/features")).json()
    assert feats["scenario"] == "ADJ-02" and feats["order_path"] == "off"


async def test_no_scenario_flag_without_the_mode(monkeypatch):
    monkeypatch.delenv("OFO_SCENARIO", raising=False)
    assert (await _get(create_app(), "/features")).json()["scenario"] is None


def test_adj19_stale_feed_reads_stale():
    p = scenario_mode.load("ADJ-19").provider
    assert p.status().health.value == "stale"
    assert p.underlying_quote("NIFTY").health.value == "stale"


async def test_adj24a_feed_missing_spot_absent_route_answers(monkeypatch):
    scn = scenario_mode.load("ADJ-24a")
    assert scn.provider.underlying_quote("NIFTY") is None
    assert scn.rest_index_quote() == (200, {"status": "success", "data": {"NSE:NIFTY 50": {
        "last_price": 23100.0, "timestamp": "2026-10-30 11:00:00"}}})
    idx = await _get(_app(monkeypatch, "ADJ-24a"), "/api/market/indices")
    assert idx.status_code == OK and idx.json()["indices"][0]["value"] is None


def test_adj24b_every_spot_source_failed():
    scn = scenario_mode.load("ADJ-24b")
    assert scn.provider.underlying_quote("NIFTY") is None
    status, reply = scn.rest_index_quote()
    assert status == GATEWAY_TIMEOUT and reply["error_type"] == "NetworkException"


# ---- broker answer states (ADJ-20a..e) -------------------------------------------------------------------------------
def _margin(sid: str) -> KiteMargin:
    scn = scenario_mode.load(sid)
    return KiteMargin(api_key="k", access_token="t", transport=scn.margin_transport)  # noqa: S106 - fake


def test_adj20a_margin_failed_is_unavailable():
    with pytest.raises(KiteMarginError, match="kite_margin_unavailable"):
        _margin("ADJ-20a")._data("POST", "/margins/basket", "[]")  # the real reply parser


def test_adj20b_margin_empty_reads_as_no_figure():
    assert _margin("ADJ-20b")._data("POST", "/margins/basket", "[]") == {}


def test_adj02_margin_stated():
    data = _margin("ADJ-02")._data("POST", "/margins/basket", "[]")
    assert data["final"]["total"] == Decimal("100000.0")


def test_adj20c_unpriced_leg_absent_from_quote_reply():
    reply = scenario_mode.load("ADJ-20c").quote_reply()
    assert "NFO:NIFTY26N0322400PE" not in reply["data"] and "NFO:NIFTY26N0322600PE" in reply["data"]


def test_adj20d_not_listed_strike_not_in_instrument_list():
    scn = scenario_mode.load("ADJ-20d")
    unlisted = [r["tradingsymbol"] for r in scn.data["market"]["chains"][0]["rows"] if not r["listed"]]
    symbols = {lc.broker_refs[0].broker_symbol for lc in scn.provider.instrument_master()}
    assert unlisted and not set(unlisted) & symbols


def test_adj20e_low_oi_unknown_carried():
    scn = scenario_mode.load("ADJ-20e")
    states = {scn.low_oi_state(i) for i in scn.rows_by_id}
    assert states == {"stated", "unknown"}


def test_clock_is_the_scenario_clock():
    assert scenario_mode.load("ADJ-02").clock() == datetime.datetime.fromisoformat("2026-11-06T11:40:00+05:30")


# ---- no order path ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("method,path", sorted(scenario_mode.ORDER_ROUTES))
async def test_every_order_route_refused(monkeypatch, method, path):
    app = _app(monkeypatch, "ADJ-02")
    monkeypatch.setenv("OFO_ORDER_PATH", "1")  # even with the order path switched on
    url = path.replace("{strategy_id}", "1").replace("{trigger_id}", "1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.request(method, url, json={})
    assert r.status_code == CONFLICT and r.json()["code"] == "USER_INPUT_026"


def test_every_mutating_route_is_classified(monkeypatch):
    monkeypatch.delenv("OFO_SCENARIO", raising=False)
    assert scenario_mode.unclassified_mutating_routes(create_app().routes) == []


def test_unclassified_route_found():
    class R:
        methods = frozenset({"POST"})
        path = "/api/new-order"
    assert scenario_mode.unclassified_mutating_routes([R()]) == [("POST", "/api/new-order")]
