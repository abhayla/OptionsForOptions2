"""GC-SET choices: the pick-lists the browser offers come from the server's own answer (REQ-167 AC-5; REQ-080 AC-1).

Spec basis: REQ-167 AC-5 "Limits (range pick-list cap and step, leg-picker widths, lot caps)"; contract: frontend values
served by the server, the browser keeps no copy. One test per key: the answer carries the value in force, the server
accepts what it offered and refuses the rest, and a changed setting changes both with no restart. The settings read goes
through the test's rolled-back connection (``get_settings_reader`` overridden), so no row is ever committed.
"""
from __future__ import annotations

import types
from decimal import Decimal
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_settings_rate_wiring import _app

WIDTH_KEYS = [f"limits.leg_picker_width_{i}" for i in range(1, 5)]
WIDTH_DEFAULTS = [10, 20, 30, 40]  # REQ-080 AC-1: the defaults never change
FIRST_WIDTH, CHANGED_WIDTH = 10, 50


async def _set(session, key: str, value: str, cid: str) -> None:
    from ofo_app import settings_store  # noqa: PLC0415

    await settings_store.add_setting(session, key, value, set_by="admin-test", correlation_id=cid)


def test_the_four_width_keys_default_to_10_20_30_40():
    from ofo import settings  # noqa: PLC0415

    registry = settings.registry()
    assert [registry[k].default for k in WIDTH_KEYS] == [Decimal(d) for d in WIDTH_DEFAULTS]
    assert {registry[k].group for k in WIDTH_KEYS} == {"Limits"}


@pytest.mark.parametrize("index", [1, 2, 3, 4])
async def test_a_changed_leg_picker_width_changes_the_answer_and_what_the_route_accepts(
        app_engine: AsyncEngine, monkeypatch, index: int):
    """Each of the four keys: default -> the answer carries [10,20,30,40] and default_width 10; the key set to 50 ->
    the next answer carries it in its place, the route accepts width 50 and refuses the width it replaced."""
    import test_leg_picker_routes as lp  # noqa: PLC0415
    from ofo_app import live_market  # noqa: PLC0415
    from ofo_app.routes import leg_picker, outcome  # noqa: PLC0415

    _provider, feed = lp.priced_provider()
    monkeypatch.setattr(live_market, "_current", types.SimpleNamespace(context=lambda: feed.ctx, feed=feed,
                                                                    running=lambda: False))
    conn = await app_engine.connect()
    trans = await conn.begin()
    try:
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
        app = _app(session)

        async def reader(_u, _e):
            return lp.catalogue()

        app.dependency_overrides[leg_picker.get_feed] = lambda: feed
        app.dependency_overrides[outcome.get_answer_clock] = lambda: (lambda: lp.T0)
        app.dependency_overrides[leg_picker.get_picker_reader] = lambda: reader
        q = {"underlying": "NIFTY", "expiry": lp.EXPIRY.isoformat()}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            first = await ac.get("/api/leg-picker/strikes", params=q)
            assert first.status_code == HTTPStatus.OK, first.text
            assert first.json()["widths"] == WIDTH_DEFAULTS and first.json()["default_width"] == FIRST_WIDTH
            assert first.json()["width"] == FIRST_WIDTH  # none asked = the first choice
            replaced = WIDTH_DEFAULTS[index - 1]
            await _set(session, WIDTH_KEYS[index - 1], str(CHANGED_WIDTH), f"gcset-width-{index}")
            second = await ac.get("/api/leg-picker/strikes", params=q)
            expected = [CHANGED_WIDTH if i == index else d for i, d in enumerate(WIDTH_DEFAULTS, 1)]
            assert second.json()["widths"] == expected, second.text
            assert second.json()["default_width"] == expected[0]
            accepted = await ac.get("/api/leg-picker/strikes", params={**q, "width": CHANGED_WIDTH})
            assert accepted.json()["width"] == CHANGED_WIDTH
            assert (await ac.get("/api/leg-picker/strikes", params={**q, "width": replaced})).status_code == (
                HTTPStatus.UNPROCESSABLE_ENTITY)
    finally:
        await trans.rollback()
        await conn.close()


@pytest.mark.parametrize(("key", "default"), [("limits.range_step", 100), ("limits.range_cap_nifty", 3000),
                                              ("limits.range_cap_sensex", 9000)])
def test_each_range_pick_list_key_defaults_exactly_and_is_read_from_the_values_in_force(key, default):
    """REQ-026 AC-5 defaults never change; the readers take the value from the mapping handed in (a changed value in the
    mapping is what the served settings answer carries to the browser)."""
    from ofo import settings  # noqa: PLC0415
    from ofo.settings import calc  # noqa: PLC0415

    values = dict(settings.defaults())
    assert values[key] == Decimal(default)
    got = (calc.range_step(values), calc.range_cap(values, "NIFTY"), calc.range_cap(values, "SENSEX"))
    assert got == (100, 3000, 9000)
    values[key] = Decimal(default + 100)
    reads = {"limits.range_step": calc.range_step(values), "limits.range_cap_nifty": calc.range_cap(values, "NIFTY"),
             "limits.range_cap_sensex": calc.range_cap(values, "SENSEX")}
    assert reads[key] == default + 100


def test_the_strikes_answer_carries_the_quick_pick_distances_in_force():
    """REQ-079 AC-7: the answer lists the distances the quick-pick route accepts, for the asked underlying only."""
    import test_leg_picker_routes as lp  # noqa: PLC0415
    from ofo.settings import calc, defaults  # noqa: PLC0415
    from ofo_app.routes.leg_picker import strikes_answer  # noqa: PLC0415

    _provider, feed = lp.priced_provider()
    out = strikes_answer(feed, "NIFTY", lp.EXPIRY, 10, lp.catalogue(), lambda: lp.T0)
    assert out.quick_pick_distances == [50, 100, 150, 200]
    values = dict(defaults())
    values["scenarios.strangle_quick_pick_nifty_2"] = Decimal(300)
    changed = strikes_answer(feed, "NIFTY", lp.EXPIRY, 10, lp.catalogue(), lambda: lp.T0,
                             quick_picks=calc.quick_pick_distances(values))
    assert changed.quick_pick_distances == [50, 300, 150, 200]
