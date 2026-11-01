"""GC-SET core, scenario mode: the scenario (a dev stand-in for live) prices with the ``pricing.risk_free_rate`` setting
in force at each request, like the live context (REQ-167 AC-1; ADR-222 (1), (9)). Replay mode and unit-test overrides
keep their own rate (see ``test_settings_rate_wiring.py`` for the live context).

Spec basis: REQ-167 AC-1 "the value in force at a time is the newest row not after that time, else the default";
ADR-222 (9) a change applies at the next check, no restart.

Answer states of the setting under the scenario: row stated (0.07) -> that rate; no row -> the registry default 0.065;
store error (SettingsError, database down) -> the route answers an error and nothing is priced (fail closed).
The app is built ONCE (``OFO_SCENARIO=ADJ-02``, APP_ENV=test) and asked twice; the 0.07 row lives only in the
rolled-back test transaction.
"""

from __future__ import annotations

from decimal import Decimal
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

KEY = "pricing.risk_free_rate"
LEGS = 2  # one call and one put at the 23400 strike


def _scenario_app(monkeypatch):
    from ofo_app.main import create_app  # noqa: PLC0415

    monkeypatch.setenv("OFO_SCENARIO", "ADJ-02")
    monkeypatch.setenv("APP_ENV", "test")
    return create_app()


def _body():
    """A two-leg strategy on the scenario's own listed contracts, planned at the scenario book's last prices."""
    from ofo_app import scenario_mode  # noqa: PLC0415

    scn = scenario_mode.load("ADJ-02")
    now = scn.clock()
    legs = []
    for lc in scn.provider.instrument_master():
        c = lc.contract
        iid = scenario_mode.instrument_id(lc)
        q = scn.provider.book.get(iid, now) if c.expiry is not None else None
        if q is None or q.ltp is None or c.strike not in (Decimal("23400"),) or c.instrument_type not in ("CE", "PE"):
            continue
        legs.append({"instrument_id": iid, "action": "SELL", "lots": 1, "planned_entry": f"{q.ltp:f}",
                     "captured_at": now.isoformat()})
    assert len(legs) == LEGS, legs
    return {"underlying": scn.data["underlying"], "legs": legs}


def _spy(monkeypatch) -> list[Decimal]:
    from ofo_app.routes import outcome  # noqa: PLC0415

    used: list[Decimal] = []
    real = outcome.read_snapshot

    def spy(provider_, underlying, ids, valuation, rate, *a, **k):
        used.append(rate)
        return real(provider_, underlying, ids, valuation, rate, *a, **k)

    monkeypatch.setattr(outcome, "read_snapshot", spy)
    return used


def _figures(out: dict) -> dict:
    return {k: v for k, v in out.items() if "at" not in k.split("_")}


async def test_core_scenario_prices_with_the_stored_rate_with_no_rebuild(app_engine: AsyncEngine, monkeypatch):
    """Core: scenario + no row -> 0.065 (figure A); a 0.07 row effective now -> the next request on the SAME app
    prices with 0.07 (figure B != A)."""
    from ofo_app import settings_store  # noqa: PLC0415
    from ofo_app.routes.outcome import get_settings_reader  # noqa: PLC0415

    used = _spy(monkeypatch)
    conn = await app_engine.connect()
    trans = await conn.begin()
    try:
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
        app = _scenario_app(monkeypatch)

        async def read():
            return await settings_store.settings_in_force(session)

        app.dependency_overrides[get_settings_reader] = lambda: read
        body = _body()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            first = await ac.post("/api/strategies/outcome", json=body)
            assert first.status_code == HTTPStatus.OK, first.text
            assert used == [Decimal("0.065")]  # scenario + no row
            await settings_store.add_setting(session, KEY, "0.07", set_by="admin-test", correlation_id="gcset-scn-1")
            second = await ac.post("/api/strategies/outcome", json=body)
            assert second.status_code == HTTPStatus.OK, second.text
        assert used == [Decimal("0.065"), Decimal("0.07")]  # scenario + row, exact Decimal, same app
        a, b = _figures(first.json()), _figures(second.json())
        assert a != b, "the stored rate did not change any figure"
        print("figures changed by the rate:", sorted(k for k in a if a[k] != b.get(k)))  # evidence line (pytest -s)
    finally:
        await trans.rollback()
        await conn.close()


async def test_scenario_store_that_cannot_answer_fails_closed(monkeypatch):
    """SettingsError or a database error under the scenario: an error answer, never a price with the default."""
    from ofo_app.routes.outcome import get_settings_reader  # noqa: PLC0415
    from ofo_app.settings_store import SettingsError  # noqa: PLC0415

    used = _spy(monkeypatch)
    body = _body()
    for exc in (SettingsError("stored setting refused"), ConnectionRefusedError("db down")):
        app = _scenario_app(monkeypatch)

        async def broken(exc=exc):
            raise exc

        app.dependency_overrides[get_settings_reader] = lambda broken=broken: broken
        async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False),
                               base_url="http://test") as ac:
            resp = await ac.post("/api/strategies/outcome", json=body)
        assert resp.status_code == HTTPStatus.INTERNAL_SERVER_ERROR, resp.text
        assert "0.065" not in resp.text
    assert used == []


async def test_scenario_context_with_the_rate_replaced_is_still_the_scenario_feed(monkeypatch):
    """``same_feed`` (issue #206 identity checks) holds for the per-request copy of the scenario context."""
    from ofo_app.routes import outcome  # noqa: PLC0415

    app = _scenario_app(monkeypatch)
    dep = app.dependency_overrides[outcome.get_market_context]

    async def read():
        from ofo import settings  # noqa: PLC0415

        return {**settings.defaults(), KEY: Decimal("0.07")}  # every setting in force; only the rate changed

    ctx = await dep(read)
    assert ctx.rate == Decimal("0.07")
    base = await dep(_default_reader)
    assert base is not ctx
    assert outcome.same_feed(ctx, base)
    assert not outcome.same_feed(ctx, None)


async def _default_reader():
    from ofo import settings  # noqa: PLC0415

    return settings.defaults()


@pytest.mark.parametrize("rate", ["0.065", "0.07"])
async def test_replace_keeps_provider_and_clock(monkeypatch, rate):
    from ofo_app.routes import outcome  # noqa: PLC0415

    ctx = outcome.MarketContext(object(), lambda: None, Decimal("0.065"))

    async def read():
        from ofo import settings  # noqa: PLC0415

        return {**settings.defaults(), KEY: Decimal(rate)}  # every setting in force; only the rate changed

    out = await outcome.with_rate_in_force(ctx, read)
    assert out.rate == Decimal(rate) and out.provider is ctx.provider and out.clock is ctx.clock
