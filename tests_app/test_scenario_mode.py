"""GC-ADJ1 step 1b (W-196): scenario mode serves an adjustment-library scenario through the real Kite parsers, only
under APP_ENV development/test, and refuses every order route."""
from __future__ import annotations

import ast
import datetime
import inspect
import re as re_mod
import sys
import textwrap
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


def _basket(*sides: str):
    from ofo_app.kite_margin import BasketOrder  # noqa: PLC0415
    syms = ("NIFTY26N0322400CE", "NIFTY26N0322600PE")
    return [BasketOrder("NFO", syms[i], s, "NRML", "LIMIT", 75, Decimal("45.55"))
            for i, s in enumerate(sides)]


def test_stated_margin_reads_through_fetch_basket_margin():
    got = _margin("ADJ-02").fetch_basket_margin(_basket("BUY", "SELL"))
    assert got.top_up == 0 and got.required_total == Decimal("100000")
    assert [o.tradingsymbol for o in got.orders] == ["NIFTY26N0322400CE", "NIFTY26N0322600PE"]


def test_failed_margin_still_unavailable_through_fetch_basket_margin():
    with pytest.raises(KiteMarginError, match="kite_margin_unavailable"):
        _margin("ADJ-20a").fetch_basket_margin(_basket("BUY"))


def test_empty_margin_still_no_figure_through_fetch_basket_margin():
    with pytest.raises(KiteMarginError, match="kite_margin_no_figure"):
        _margin("ADJ-20b").fetch_basket_margin(_basket("SELL"))


def test_funds_call_is_served_per_state():
    assert _margin("ADJ-02").fetch_available_funds() == Decimal("10000000")
    with pytest.raises(KiteMarginError, match="kite_margin_no_figure"):
        _margin("ADJ-20b").fetch_available_funds()
    with pytest.raises(KiteMarginError, match="kite_margin_unavailable"):
        _margin("ADJ-20a").fetch_available_funds()


def test_exchange_token_start_is_above_every_twin():
    assert scenario_mode._first_free_exchange_token(None) == scenario_mode._FIRST_TOKEN
    above = scenario_mode._FIRST_TOKEN + 10
    assert scenario_mode._first_free_exchange_token({"A": (1, above)}) == above
    assert scenario_mode._first_free_exchange_token({"A": (1, 7)}) == scenario_mode._FIRST_TOKEN


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


def test_settings_refuse_scenario_when_app_env_unset(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    with pytest.raises(ValueError, match="development/test-only"):
        Settings(DATABASE_URL=DB, OFO_SCENARIO="ADJ-02", _env_file=None)


# ---- structural: a route that reaches an order write is an ORDER route -----------------------------------------------
#: What places, changes or cancels an order (paper or real). Reaching one makes a route an order route.
ORDER_SINKS = {("ofo_app.paper_store", "place")}
#: A call the scan cannot resolve whose name looks like an order action is treated as one (fail closed).
ORDERISH = re_mod.compile(r"(^|_)(place|cancel|modify)(_|$)|order|basket", re_mod.IGNORECASE)
_UNRESOLVED = object()


def _resolve(node, scope):
    if isinstance(node, ast.Name):
        return scope.get(node.id, _UNRESOLVED)
    if isinstance(node, ast.Attribute):
        base = _resolve(node.value, scope)
        return _UNRESOLVED if base is _UNRESOLVED else getattr(base, node.attr, _UNRESOLVED)
    return _UNRESOLVED


def _last_name(node) -> str:
    return node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else ""


def reaches_order(fn, seen: set) -> bool:
    """True when ``fn`` (transitively, within ofo_app) calls an ORDER_SINK, or calls an unresolvable order-like name."""
    fn = inspect.unwrap(fn)
    key = (getattr(fn, "__module__", ""), getattr(fn, "__qualname__", ""))
    if key in seen:
        return False
    seen.add(key)
    if (key[0], getattr(fn, "__name__", "")) in ORDER_SINKS:
        return True
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    except (OSError, TypeError):
        return False
    scope = vars(sys.modules[fn.__module__])
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = _resolve(node.func, scope)
        if target is _UNRESOLVED:
            if ORDERISH.search(_last_name(node.func)):
                return True  # fail closed: an order-like call the scan cannot follow
            continue
        mod = getattr(inspect.unwrap(target), "__module__", "") or ""
        if callable(target) and mod.startswith("ofo_app") and reaches_order(target, seen):
            return True
    return False


def test_every_route_reaching_an_order_write_is_an_order_route(monkeypatch):
    monkeypatch.delenv("OFO_SCENARIO", raising=False)
    found = set()
    for r in create_app().routes:
        for m in getattr(r, "methods", None) or ():
            if m in scenario_mode.MUTATING_METHODS and reaches_order(r.endpoint, set()):
                found.add((m, r.path))
    assert found - scenario_mode.ORDER_ROUTES == set()
    assert ("POST", "/strategies/{strategy_id}/tracking/exit") in found  # the scan sees the checker's case


def test_the_scan_follows_a_call_into_the_paper_store():
    from ofo_app.routes import tracking  # noqa: PLC0415
    assert reaches_order(tracking.exit_tracking, set())


# ---- a scenario contract with a catalogue twin is served under the catalogue's own token ---------------------
def test_catalogue_twin_served_under_real_token_others_synthetic(monkeypatch):
    rows = scenario_mode.load("ADJ-02").data["market"]["chains"][0]["rows"]
    twin, other = rows[0]["tradingsymbol"], rows[1]["tradingsymbol"]
    real_token, real_ex = 1_234_567 * 256 + 2, 1_234_567
    monkeypatch.setattr(scenario_mode, "catalogue_twins", lambda symbols: {twin: (real_token, real_ex)})
    scn = scenario_mode.load("ADJ-02")
    by_symbol = {lc.broker_refs[0].broker_symbol: lc for lc in scn.provider.instrument_master()}
    assert int(by_symbol[twin].broker_refs[0].broker_token) == real_token
    assert by_symbol[twin].contract.exchange_token == real_ex
    assert by_symbol[other].contract.exchange_token >= scenario_mode._FIRST_TOKEN  # no twin: keeps the synthetic token
    assert scenario_mode.instrument_id(by_symbol[twin]) in scn.rows_by_id  # priced under the real id


WANTED = [("S", "NFO", "2026-11-09", 23500, "CE")]


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(broker_symbol="S", broker_token=2560, exchange_token=10, exchange_segment="NSE_FO",
                             expiry=datetime.date(2026, 11, 9), strike=Decimal("23500.00"), instrument_type="CE")
        self.__dict__.update(kw)


def test_unreadable_catalogue_keeps_every_token_synthetic(monkeypatch):
    async def down(symbols):
        raise OSError("no db")

    monkeypatch.setattr(scenario_mode, "_database_name", lambda: "ofo_dev")
    monkeypatch.setattr(scenario_mode, "_read_twins", down)
    assert scenario_mode.catalogue_twins(WANTED) == {}


def test_twin_carrying_a_would_be_synthetic_token_collides_with_nothing(monkeypatch):
    rows = scenario_mode.load("ADJ-02").data["market"]["chains"][0]["rows"]
    would_be = scenario_mode._FIRST_TOKEN + 1  # exactly the first synthetic exchange token
    monkeypatch.setattr(scenario_mode, "catalogue_twins",
                        lambda wanted: {rows[0]["tradingsymbol"]: (would_be * 256 + 2, would_be)})
    master = scenario_mode.load("ADJ-02").provider.instrument_master()
    tokens = [int(lc.broker_refs[0].broker_token) for lc in master]
    assert len(tokens) == len(set(tokens))
    assert len({lc.contract.exchange_token for lc in master}) == len(master)


def test_forced_duplicate_token_refuses_scenario_mode():
    row = {"instrument_token": "1", "exchange_token": "7", "tradingsymbol": "A", "exchange": "NFO"}
    with pytest.raises(ScenarioRefused, match="collision"):
        scenario_mode.check_no_repeated_token([row, {**row, "tradingsymbol": "B", "exchange_token": "8"}])
    with pytest.raises(ScenarioRefused, match="collision"):
        scenario_mode.check_no_repeated_token([row, {**row, "tradingsymbol": "B", "instrument_token": "2"}])


def test_twin_must_agree_on_exchange_expiry_strike_and_type():
    assert scenario_mode.match_twins([_Row()], WANTED) == {"S": (2560, 10)}
    for off in ({"exchange_segment": "BSE_FO"}, {"expiry": datetime.date(2026, 11, 16)}, {"strike": Decimal("23600")},
                {"instrument_type": "PE"}):
        assert scenario_mode.match_twins([_Row(**off)], WANTED) == {}


def test_two_active_catalogue_rows_for_one_symbol_give_no_twin():
    assert scenario_mode.match_twins([_Row(), _Row(broker_token=5120, exchange_token=20)], WANTED) == {}


def test_other_database_reads_no_twins(monkeypatch):
    async def fail(symbols):
        pytest.fail("must not read")

    monkeypatch.setattr(scenario_mode, "_database_name", lambda: "ofo_prod")
    monkeypatch.setattr(scenario_mode, "_read_twins", fail)
    assert scenario_mode.catalogue_twins(WANTED) == {}
