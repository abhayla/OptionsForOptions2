"""Lane FD3 item 4 (ADR-016 to ADR-019; D-36 (c)): the real door gives its pooled connection back before EVERY Zerodha or
market wait, and the return takes the strategy lock only AFTER them. The double-order guard is unchanged: ``record_plan``
takes the lock again and re-checks (open plan, number above the highest, tag taken). Real PostgreSQL, rolled back."""
from __future__ import annotations

from http import HTTPStatus

import pytest
from ofo_app.routes import execute as ex_route
from ofo_app.routes import execution_return as ret_route
from test_execution_return import _app_for, _data, _market, _post, _Reads, _sold, _store_plan


async def test_off_loop_gives_the_connection_back_before_the_thread_runs():
    seen: list[str] = []

    class Db:
        async def commit(self):
            seen.append("release")

    def wait():
        seen.append("wait")
        return 7

    req = ex_route._Request(Db(), "u", 1, "ENTRY", None, None, None, None, None)
    assert await ex_route._off_loop(req, wait) == 7
    assert seen == ["release", "wait"]


@pytest.mark.usefixtures("app_engine", "order_path_on")
async def test_the_return_reads_zerodha_and_the_market_before_it_takes_the_lock(app_engine, admin_engine, monkeypatch):
    from ofo_app import adjustment_readers  # noqa: PLC0415
    from ofo_app.routes import outcome  # noqa: PLC0415
    from test_execute_route import _strategy_one  # noqa: PLC0415
    from test_strategy_store import _user  # noqa: PLC0415

    order: list[str] = []
    real_read, real_lock, real_release = ret_route._read_zerodha, ret_route.store.lock_strategy, ret_route.release_connection

    def read(req, catalogue):
        order.append("zerodha")
        return real_read(req, catalogue)

    async def lock(*a, **k):
        order.append("lock")
        return await real_lock(*a, **k)

    async def release(db):
        order.append("release")
        return await real_release(db)

    async def iv(*_a):
        order.append("market")
        return None

    monkeypatch.setattr(ret_route, "_read_zerodha", read)
    monkeypatch.setattr(ret_route.store, "lock_strategy", lock)
    monkeypatch.setattr(ret_route, "release_connection", release)
    monkeypatch.setattr(adjustment_readers, "atm_iv_now", iv)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_CATALOGUE_DATE", "2026-10-16")
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user = _user()
            sid = await _strategy_one(conn, user, app_engine.url.username)
            await _store_plan(conn, user, sid, ("ENTRY", "SELL", "5.45"))
            reads = _Reads("122104", orders=_sold(_data("orders-122104")), trades=_sold(_data("trades-122104")))
            app = _app_for(conn, user, reads)
            from test_execution_return import ENTRY_SPOT  # noqa: PLC0415
            app.dependency_overrides[outcome.get_market_context] = lambda: _market(ENTRY_SPOT)
            order.clear()  # the setup above locks too
            resp = await _post(app, sid)
            assert resp.status_code == HTTPStatus.OK, resp.text
        finally:
            await trans.rollback()
    assert order.index("release") < order.index("zerodha") < order.index("market") < order.index("lock"), order
