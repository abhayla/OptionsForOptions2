"""GC-ICSAFE c36 (issue #682): a screen request uses ONE database connection.

The pool is cut to one connection (no overflow, 2 s wait). A request that holds its own session while a reader opens a
second one waits for a connection that never frees up, so it times out ("QueuePool limit of size 1 overflow 0
reached"). Both routes below must answer: the paper order (a stored paper strategy's open leg is exited) and the
adjustment check. Guards the class: any new reader that opens a second session inside these two requests turns this red.
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


async def test_each_route_answers_with_a_pool_of_one_connection(app_engine, monkeypatch, caplog):
    monkeypatch.setenv("DATABASE_URL", app_engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OFO_SCENARIO", PATH_ID)
    _reset_engine()
    try:
        await _walk(app_engine, monkeypatch, caplog)
    finally:
        await app_db.close_db()
        _reset_engine()
        scenario_mode._loaded.clear()


async def _walk(app_engine, monkeypatch, caplog) -> None:
    await load_library(app_engine)
    await app_engine.dispose()
    sid = await seed_mod.seed(PATH_ID)  # a stored paper strategy, built on the default pool
    await app_db.close_db()
    monkeypatch.setenv("DB_POOL_SIZE", "1")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "0")
    real_create = app_db.create_async_engine
    monkeypatch.setattr(app_db, "create_async_engine",
                        lambda url, **kw: real_create(url, **kw, pool_timeout=POOL_WAIT_SECONDS))
    _reset_engine()
    assert app_db.get_engine().pool.size() == 1
    async with app_db.get_engine().begin() as conn:
        await scenario_mode.write_frame(conn, PATH_ID, 0)
        net = {int(c): int(n) for c, n in (await conn.execute(text(
            "SELECT contract_id, sum(CASE WHEN side = 'BUY' THEN quantity ELSE -quantity END) "
            "FROM public.paper_orders WHERE strategy_id = :s GROUP BY contract_id"), {"s": sid})).all()}
    cid, held = next((c, n) for c, n in net.items() if n != 0)
    leg_exit = {"contract_id": cid, "side": "SELL" if held > 0 else "BUY", "quantity": abs(held), "price": "1.00",
                "kind": "exit"}

    from ofo_app.main import create_app  # noqa: PLC0415 - after the environment above
    scenario_mode._loaded.clear()
    app = create_app()
    answers: dict[str, str] = {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        with contextlib.suppress(Exception):  # untimed warm-up: the scenario's cold start is not the route's time
            await ac.get(f"/api/strategies/{sid}/adjustment-check")
        for name, want, call in (
                ("adjustment-check", 200, lambda: ac.get(f"/api/strategies/{sid}/adjustment-check")),
                ("paper order", 201, lambda: ac.post(f"/paper/strategies/{sid}/orders", json={"orders": [leg_exit]}))):
            started = time.monotonic()
            try:
                r = await call()
                took = time.monotonic() - started
                ok = r.status_code == want and took < ANSWER_WITHIN_SECONDS
                answers[name] = f"{'ok' if ok else 'BAD'} status={r.status_code} took={took:.2f}s {r.text[:200]}"
            except Exception as exc:  # noqa: BLE001 - the pool timeout is the failure this test names
                answers[name] = f"BAD {type(exc).__name__}: {str(exc)[:200]}"
    bad = {k: v for k, v in answers.items() if not v.startswith("ok")}
    assert not bad, f"answers: {answers}"
    assert "QueuePool" not in caplog.text
    log.info("answers: %s", answers)
