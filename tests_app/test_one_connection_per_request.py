"""GC-ICSAFE c36, c38, c50 (issue #682): a request uses ONE database connection.

The pool is cut to one connection (no overflow, 2 s wait). A request that holds its own session while a reader opens a
second one waits for a connection that never frees up, so it times out ("QueuePool limit of size 1 overflow 0
reached"). Both tests undo the conftest's "no database" stubs, so the settings read and the charge-rates read are the
real ones. Routes called: Execute (ENTRY), and in scenario mode the adjustment check, approaches, history, plan read,
alert style read and the paper order. Not called here (need a body or a state of their own): the plan save and edit,
the alert style pin, the playbook test route and the tracking exit. Any new reader that opens a second session inside
a called route turns this red.
"""
from __future__ import annotations

import contextlib
import importlib.util
import logging
import pathlib
import time

from _scenario_catalogue import load_library
from httpx import ASGITransport, AsyncClient
from ofo_app import db as app_db
from ofo_app import scenario_mode
from ofo_app.config import get_settings
from sqlalchemy import text

log = logging.getLogger(__name__)
ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("seed_scenario", ROOT / "scripts" / "seed_scenario.py")
seed_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_mod)
PATH_ID = "PATH-01"
POOL_WAIT_SECONDS = 2
ANSWER_WITHIN_SECONDS = 5


def _reset_engine() -> None:
    app_db.get_sessionmaker.cache_clear()
    app_db.get_engine.cache_clear()
    get_settings.cache_clear()


async def _pool_of_one(monkeypatch) -> None:
    monkeypatch.setenv("DB_POOL_SIZE", "1")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "0")
    real_create = app_db.create_async_engine
    monkeypatch.setattr(app_db, "create_async_engine",
                        lambda url, **kw: real_create(url, **kw, pool_timeout=POOL_WAIT_SECONDS))
    _reset_engine()
    assert app_db.get_engine().pool.size() == 1


async def _ask(want: int, call, within: float = ANSWER_WITHIN_SECONDS) -> str:
    started = time.monotonic()
    try:
        r = await call()
        took = time.monotonic() - started
        ok = r.status_code == want and took < within
        return f"{'ok' if ok else 'BAD'} status={r.status_code} took={took:.2f}s {r.text[:200]}"
    except Exception as exc:  # noqa: BLE001 - the pool timeout is the failure this test names
        return f"BAD {type(exc).__name__}: {str(exc)[:200]}"


async def test_execute_answers_with_a_pool_of_one_connection(app_engine, admin_engine, monkeypatch, caplog):
    """Execute ENTRY on the owner's recorded 2026-10-16 order: the freeze-stale setting is read on the request's own
    session. Runs first: it stores strategy id 1, which it removes again."""
    from ofo_app.execute_replay import AT, store_strategy_one  # noqa: PLC0415
    from ofo_app.routes import execute as route  # noqa: PLC0415
    from test_execute_route import RATES, _Quotes, _Replay, _session_for  # noqa: PLC0415
    from test_strategy_store import _app, _remove_own_rows, _user  # noqa: PLC0415

    monkeypatch.undo()  # the conftest's "settings = defaults, no database" patch would hide the second session
    for name, value in (("DATABASE_URL", app_engine.url.render_as_string(hide_password=False)), ("APP_ENV", "test"),
                        ("OFO_ORDER_PATH", "1"), ("TEST_CATALOGUE_DATE", "2026-10-16")):
        monkeypatch.setenv(name, value)
    user = _user()
    async with admin_engine.begin() as conn:
        sid = await store_strategy_one(conn, user, app_engine.url.username)
        cid = (await conn.execute(text("SELECT contract_id FROM public.broker_instruments "
                                       "WHERE broker_symbol = 'NIFTY26O1923650CE'"))).scalar_one()
    _reset_engine()
    try:
        await _pool_of_one(monkeypatch)
        app = _app(app_db.get_sessionmaker(), user)
        app.dependency_overrides[route.get_quote_reader] = _Quotes
        app.dependency_overrides[route.get_execute_clock] = lambda: (lambda: AT)
        app.dependency_overrides[route.load_charge_rates] = lambda: RATES
        entry = _Replay(funds="1003", basket_total="354.25", orders=None, positions="positions-151006")
        app.dependency_overrides[route.get_kite_session] = lambda: _session_for(entry)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            # a pool timeout here is a 500; the cold start of the recorded Kite session is not the route's time
            answer = await _ask(200, lambda: ac.post(f"/strategies/{sid}/execute",
                                                     json={"action": "ENTRY", "revision": 1}), within=30)
        assert answer.startswith("ok"), answer
        assert "QueuePool" not in caplog.text
    finally:
        await app_db.close_db()
        _reset_engine()
        await _remove_own_rows(admin_engine, [int(cid)], user)


async def test_each_route_answers_with_a_pool_of_one_connection(app_engine, admin_engine, monkeypatch, caplog):
    """Scenario mode (the paper-order route's scenario guard runs first), with the REAL settings and charge-rates reads:
    the conftest's two "no database" stubs are undone, and the rates cache is emptied before every call."""
    monkeypatch.undo()
    monkeypatch.setenv("DATABASE_URL", app_engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OFO_SCENARIO", PATH_ID)
    _reset_engine()
    seeded: dict[str, int] = {}
    try:
        await _walk(app_engine, monkeypatch, caplog, seeded)
    finally:
        await app_db.close_db()
        _reset_engine()
        scenario_mode._loaded.clear()
        if seeded:  # the seed is idempotent and stays; the order the paper-order call placed does not
            async with admin_engine.begin() as conn:
                await conn.execute(text("SET LOCAL session_replication_role = replica"))
                await conn.execute(text("DELETE FROM public.paper_orders WHERE strategy_id = :s AND id > :after"),
                                   seeded)


async def _walk(app_engine, monkeypatch, caplog, seeded: dict[str, int]) -> None:
    await load_library(app_engine)
    await app_engine.dispose()
    sid = await seed_mod.seed(PATH_ID)  # a stored paper strategy, built on the default pool
    await app_db.close_db()
    await _pool_of_one(monkeypatch)
    async with app_db.get_engine().begin() as conn:
        await scenario_mode.write_frame(conn, PATH_ID, 0)
        net = {int(c): int(n) for c, n in (await conn.execute(text(
            "SELECT contract_id, sum(CASE WHEN side = 'BUY' THEN quantity ELSE -quantity END) "
            "FROM public.paper_orders WHERE strategy_id = :s GROUP BY contract_id"), {"s": sid})).all()}
        seeded.update(s=sid, after=(await conn.execute(text("SELECT max(id) FROM public.paper_orders WHERE "
                                                            "strategy_id = :s"), {"s": sid})).scalar_one())
    cid, held = next((c, n) for c, n in net.items() if n != 0)
    leg_exit = {"contract_id": cid, "side": "SELL" if held > 0 else "BUY", "quantity": abs(held), "price": "1.00",
                "kind": "exit"}

    from ofo_app.main import create_app  # noqa: PLC0415 - after the environment above
    from ofo_app.routes import outcome  # noqa: PLC0415 - after the placeholders of the conftest
    scenario_mode._loaded.clear()
    app = create_app()
    answers: dict[str, str] = {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        with contextlib.suppress(Exception):  # untimed warm-up: the scenario's cold start is not the route's time
            await ac.get(f"/api/strategies/{sid}/adjustment-check")
        for name, want, call in (
                ("adjustment-check", 200, lambda: ac.get(f"/api/strategies/{sid}/adjustment-check")),
                ("adjustment-approaches", 200, lambda: ac.post(f"/api/strategies/{sid}/adjustment-approaches",
                                                               json={})),
                ("adjustment-history", 200, lambda: ac.get(f"/api/strategies/{sid}/adjustment-history")),
                ("adjustment-plan", 200, lambda: ac.get(f"/api/strategies/{sid}/adjustment-plan")),
                ("alert-style", 200, lambda: ac.get(f"/api/strategies/{sid}/alert-style")),
                ("paper order", 201, lambda: ac.post(f"/paper/strategies/{sid}/orders", json={"orders": [leg_exit]}))):
            outcome._rates_cache.update(until=0.0, value=None, flight=None)  # the real charge-rates read, every call
            answers[name] = await _ask(want, call)
    bad = {k: v for k, v in answers.items() if not v.startswith("ok")}
    assert not bad, f"answers: {answers}"
    assert "QueuePool" not in caplog.text
    log.info("answers: %s", answers)
