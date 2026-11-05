"""IC e2e paper contract Stage A, the guards around the core (design decisions 1, 2, 4, 5, 7, 17). No database: the
marker read that fails is itself an answer state (refused). Database cases are in test_ic_paper_loop_core.py."""
from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil

import pytest
from httpx import ASGITransport, AsyncClient
from ofo_app import background, scenario_guard, scenario_mode

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB = "postgresql+asyncpg://example@127.0.0.1:1/x"
NOT_FOUND, UNPROCESSABLE, CONFLICT = 404, 422, 409


def _app(monkeypatch, scenario: str | None):
    from ofo_app.config import get_settings  # noqa: PLC0415
    from ofo_app.main import create_app  # noqa: PLC0415
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", DB)
    if scenario is None:
        monkeypatch.delenv("OFO_SCENARIO", raising=False)
    else:
        monkeypatch.setenv("OFO_SCENARIO", scenario)
    get_settings.cache_clear()
    scenario_mode._loaded.clear()
    return create_app()


# ---- decision 4 / 17: the lister lists each side only -------------------------------------------------------------
@pytest.mark.parametrize(("marker", "mode", "listed"), [
    (None, None, True),  # a real strategy in a live worker: listed exactly as before (decision 17)
    ("PATH-01", None, False),  # a scenario strategy in a live worker: never
    ("PATH-01", "PATH-01", True),  # its own scenario
    (None, "PATH-01", False),  # a real strategy in a scenario worker: never
    ("ADJ-02", "PATH-01", False),  # another scenario
])
def test_lister_isolation_both_ways(marker, mode, listed):
    assert background.listable(marker, mode) is listed


@pytest.mark.parametrize(("marker", "current", "refused"), [
    (None, None, False), ("PATH-01", None, True), ("PATH-01", "PATH-01", False), (None, "PATH-01", True),
    ("ADJ-02", "PATH-01", True), (scenario_guard._ABSENT, None, False), (scenario_guard._ABSENT, "PATH-01", False),
])
def test_screen_check_refuses_each_cross_case(marker, current, refused):
    assert scenario_guard.isolation_refusal(marker, current) is refused


# ---- decision 5: the guard split, wired and fail closed -----------------------------------------------------------
def test_order_route_sets_split_and_cover_every_order_route():
    real = {("POST", "/strategies/{strategy_id}/execute"), ("POST", "/strategies/{strategy_id}/execution/return")}
    assert real == scenario_mode.REAL_ORDER_ROUTES
    assert scenario_mode.REAL_ORDER_ROUTES.isdisjoint(scenario_mode.PAPER_ORDER_ROUTES)
    assert scenario_mode.ORDER_ROUTES == scenario_mode.REAL_ORDER_ROUTES | scenario_mode.PAPER_ORDER_ROUTES
    assert ("POST", "/api/scenario/frame") in scenario_mode.NON_ORDER_ROUTES


def test_every_order_route_carries_its_guard(monkeypatch):
    app = _app(monkeypatch, None)
    assert scenario_mode.misguarded_order_routes(app.routes) == []


def test_a_paper_route_without_its_guard_is_found(monkeypatch):
    """Mutation: the paper guard removed from one paper route -> start-up refuses that route."""
    app = _app(monkeypatch, None)
    route = next(r for r in app.routes if getattr(r, "path", "") == "/paper/strategies/{strategy_id}/orders")
    route.dependant.dependencies = [d for d in route.dependant.dependencies
                                    if d.call is not scenario_guard.guard_paper_order]
    assert scenario_mode.misguarded_order_routes(app.routes) == [("POST", "/paper/strategies/{strategy_id}/orders")]


def test_a_real_route_without_its_refusal_is_found(monkeypatch):
    """Mutation: the real-route refusal removed from Execute -> start-up refuses that route."""
    from ofo_app.order_path_switch import require_order_path  # noqa: PLC0415
    app = _app(monkeypatch, None)
    route = next(r for r in app.routes if getattr(r, "path", "") == "/strategies/{strategy_id}/execute")

    def strip(dep):
        dep.dependencies = [d for d in dep.dependencies
                            if d.call not in (require_order_path, scenario_mode.refuse_orders)]
        for d in dep.dependencies:
            strip(d)
    strip(route.dependant)
    assert ("POST", "/strategies/{strategy_id}/execute") in scenario_mode.misguarded_order_routes(app.routes)


def test_a_new_mutating_route_in_neither_set_blocks_start_up():
    class R:
        methods = frozenset({"POST"})
        path = "/paper/strategies/{strategy_id}/new-paper-thing"
    assert scenario_mode.unclassified_mutating_routes([R()]) == [("POST", R.path)]


@pytest.mark.parametrize("path", ["/paper/strategies/1/orders", "/paper/strategies/1/triggers",
                                  "/strategies/1/tracking/exit"])
async def test_paper_route_refused_when_the_marker_cannot_be_read(monkeypatch, path):
    """Scenario mode, no reachable database: the marker is unreadable -> 409 scenario_no_orders (fail closed)."""
    app = _app(monkeypatch, "PATH-01")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.post(path, json={})
    assert r.status_code == CONFLICT and r.json()["code"] == "USER_INPUT_026", r.text


@pytest.mark.parametrize("path", ["/strategies/1/execute", "/strategies/1/execution/return"])
async def test_real_route_refused_in_a_path_scenario(monkeypatch, path):
    monkeypatch.setenv("OFO_ORDER_PATH", "1")
    app = _app(monkeypatch, "PATH-01")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.post(path, json={})
    assert r.status_code == CONFLICT and r.json()["code"] == "USER_INPUT_026", r.text


# ---- decision 7: the worker refuses scenario mode outside development/test ----------------------------------------
@pytest.mark.parametrize("env", ["production", "staging", "Test", ""])
def test_worker_refuses_scenario_outside_dev_or_test(monkeypatch, env):
    monkeypatch.setenv("OFO_SCENARIO", "PATH-01")
    monkeypatch.setenv("APP_ENV", env)
    with pytest.raises(scenario_mode.ScenarioRefused):
        background.refuse_scenario_outside_dev_or_test()


def test_worker_live_mode_starts_no_scenario_refusal(monkeypatch):
    monkeypatch.delenv("OFO_SCENARIO", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    background.refuse_scenario_outside_dev_or_test()  # live mode: nothing to refuse


def test_scenario_worker_uses_the_scenario_feed():
    scn = scenario_mode.load("PATH-01")
    provider, step = background.scenario_worker_parts(scn, None)
    assert provider is scn.provider and callable(step)


# ---- decision 2: the frame route -----------------------------------------------------------------------------------
async def test_frame_route_is_404_when_scenario_mode_is_off(monkeypatch):
    app = _app(monkeypatch, None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.post("/api/scenario/frame", json={"frame": 1})
    assert r.status_code == NOT_FOUND, r.text


@pytest.mark.parametrize("frame", [-1, 10])
async def test_frame_route_refuses_a_frame_outside_the_path(monkeypatch, frame):
    app = _app(monkeypatch, "PATH-01")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.post("/api/scenario/frame", json={"frame": frame})
    assert r.status_code == UNPROCESSABLE, r.text


# ---- decision 1: path scenarios -------------------------------------------------------------------------------------
def test_path_ids_accepted_by_the_one_reader_and_malformed_ones_refused():
    assert scenario_mode.scenario_path("PATH-01").name == "frame-000.json"
    assert scenario_mode.last_frame("PATH-01") == 9  # noqa: PLR2004 - ten frames
    for bad in ("PATH-1", "PATH-01/../ADJ-02", "path-01", "PATH-99"):
        with pytest.raises(scenario_mode.ScenarioRefused):
            scenario_mode.scenario_path(bad)
    for frame in (-1, 10, True):
        with pytest.raises(scenario_mode.ScenarioRefused):
            scenario_mode.frame_path("PATH-01", frame)


def test_moving_a_path_feeds_the_frame_through_the_real_parser():
    scn = scenario_mode.load("PATH-01")
    assert str(scn.provider.underlying_quote("NIFTY").ltp) == "23290"
    scn.move_to(6)
    assert scn.frame == 6 and str(scn.provider.underlying_quote("NIFTY").ltp) == "23390"  # noqa: PLR2004
    assert scn.clock().isoformat() == "2026-11-06T11:40:00+05:30"
    assert scn.clock_box == [scn.clock()]  # the provider clock reads this box


def test_path_frames_regenerate_to_the_same_json(tmp_path):
    spec = importlib.util.spec_from_file_location("adjust_scenarios_gen", ROOT / "tests" / "adjust_scenarios_gen.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    shutil.copy(gen.PATHS_DIR / "PATH-01.json", tmp_path / "PATH-01.json")
    names = gen.generate_paths(tmp_path, gen.OUT_DIR)
    assert len(names) == 10  # noqa: PLR2004
    for name in names:
        fresh, committed = (json.loads((d / name).read_text(encoding="utf-8")) for d in (tmp_path, gen.PATHS_DIR))
        assert fresh == committed, name  # parsed JSON: line endings (checkout CRLF) do not count


# ---- fix round 1: ONE isolation helper for every background reader; scenario never with LIVE_MARKET
@pytest.mark.parametrize(("mode", "clause", "params"), [
    (None, "s.scenario_id IS NULL", {}),
    ("PATH-01", "s.scenario_id = :scope_scenario_id", {"scope_scenario_id": "PATH-01"}),
])
def test_scope_clause_is_the_sql_twin_of_in_scope(monkeypatch, mode, clause, params):
    if mode is None:
        monkeypatch.delenv("OFO_SCENARIO", raising=False)
    else:
        monkeypatch.setenv("OFO_SCENARIO", mode)
    assert scenario_mode.scope_clause("s") == (clause, params)
    assert background.listable(None, mode) is (mode is None)


@pytest.mark.parametrize("alias", ["s; DROP TABLE x", "", "S", "s.x"])
def test_scope_clause_refuses_anything_but_a_constant_alias(alias):
    with pytest.raises(ValueError, match="not a SQL alias"):
        scenario_mode.scope_clause(alias)


def test_api_refuses_scenario_with_live_market(monkeypatch):
    monkeypatch.setenv("LIVE_MARKET", "1")
    with pytest.raises(scenario_mode.ScenarioRefused, match="LIVE_MARKET"):
        _app(monkeypatch, "PATH-01")


def test_worker_refuses_scenario_with_live_market(monkeypatch):
    monkeypatch.setenv("OFO_SCENARIO", "PATH-01")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LIVE_MARKET", "1")
    with pytest.raises(scenario_mode.ScenarioRefused, match="LIVE_MARKET"):
        background.refuse_scenario_outside_dev_or_test()
