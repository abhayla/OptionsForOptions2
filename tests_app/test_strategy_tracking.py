"""W-122 over HTTP on the recorded replay (REQ-109 AC-1, AC-2, AC-3; REQ-045 AC-1, AC-2).

The saved strategy is test_strategy_store's iron condor (65 units a leg, expiry 2026-10-13): SELL 22800 CE,
BUY 23000 CE, SELL 22400 PE, BUY 22200 PE. The market is the real 2026-10-08 recording (tests/fixtures/kite_ws)
valued at its last frame 09:20:09 IST, NIFTY 50 at 22,533.25; the recorded LTPs there are 39.15, 12.95, 82.75 and 35.80.
"""
from __future__ import annotations

import datetime
import pathlib
import sys
from decimal import Decimal
from http import HTTPStatus

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay  # noqa: E402
from ofo_app.routes import tracking as tracking_routes  # noqa: E402
from ofo_app.routes.outcome import MarketContext, get_answer_clock, get_market_context  # noqa: E402
from ofo_app.routes.planned_entry import get_live_feed  # noqa: E402
from test_strategy_store import _app, _client, _user, _with_draft  # noqa: E402

D = Decimal
IDS = ["NSE_FO:44624", "NSE_FO:44632", "NSE_FO:44604", "NSE_FO:44595"]
ANSWERED = datetime.datetime(2026, 10, 8, 4, 0, tzinfo=datetime.UTC)


def _frame(provider, instrument_id: str, rupees: str) -> bytes:
    token = provider._token_of[instrument_id]
    return (1).to_bytes(2, "big") + (8).to_bytes(2, "big") + token.to_bytes(4, "big") + \
        int(D(rupees) * 100).to_bytes(4, "big")


def _market():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    provider.drain_subscription_changes()
    last = replay(provider, clock)
    return provider, clock, last


THRESHOLD = D("0.6")


async def _setup(app_engine, *, ctx="replay", threshold=THRESHOLD):
    user = _user()
    async with app_engine.connect() as conn:
        _, stored = await _with_draft(conn, user)
        await conn.commit()
    provider, clock, last = _market()
    app = _app(async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False), user)
    context = MarketContext(provider, lambda: last, D("0.065")) if ctx == "replay" else None
    app.dependency_overrides[get_market_context] = lambda: context
    app.dependency_overrides[get_live_feed] = lambda: None
    app.dependency_overrides[get_answer_clock] = lambda: lambda: ANSWERED
    app.dependency_overrides[tracking_routes.get_near_level_threshold] = lambda: threshold
    return app, stored, provider, clock, last


async def _rows(app_engine, strategy_id: int) -> tuple[int, int]:
    async with app_engine.connect() as conn:
        a = (await conn.execute(text("SELECT count(*) FROM public.strategy_tracking WHERE strategy_id = :i"),
                                {"i": strategy_id})).scalar_one()
        b = (await conn.execute(text("SELECT count(*) FROM public.strategy_tracking_legs WHERE strategy_id = :i"),
                                {"i": strategy_id})).scalar_one()
    return int(a), int(b)


async def test_ac1_ac2_core_proof_start_stores_entry_and_view_gives_paper_pnl_and_one_detection(app_engine):
    """AC-1/AC-2 core proof (REQ-045 AC-1/AC-2 too). Start stores the recorded LTPs 39.15 / 12.95 / 82.75 / 35.80 as
    the entry. The feed then moves the legs to 45.15 / 14.95 / 70.75 / 30.80. By hand: (39.15 - 45.15) x 65 = -390.00;
    (14.95 - 12.95) x 65 = +130.00; (82.75 - 70.75) x 65 = +780.00; (30.80 - 35.80) x 65 = -325.00 -> +195.00.
    Threshold 0.6: short strike 22400 vs 22533.25 = 133.25 points = 133.25 / 22533.25 x 100 = 0.5913 -> 0.59% fires,
    labelled 'Adjustment opportunity detected'; 22800 (1.18%) and the breakevens 22326.85 (0.92%) / 22873.15 (1.51%)
    do not (credit 73.15 = 39.15 - 12.95 + 82.75 - 35.80)."""
    app, stored, provider, _clock, last = await _setup(app_engine)
    async with _client(app) as c:
        started = await c.post(f"/strategies/{stored.id}/tracking", json={"revision": stored.revision})
        assert started.status_code == HTTPStatus.CREATED, started.text
        assert [leg["entry_price"] for leg in started.json()["legs"]] == ["39.15", "12.95", "82.75", "35.80"]
        assert started.json()["paper_pnl"] == "0.00"
        for iid, rupees in zip(IDS, ["45.15", "14.95", "70.75", "30.80"], strict=True):
            provider.on_frame(_frame(provider, iid, rupees), last)
        view = (await c.get(f"/strategies/{stored.id}/tracking")).json()
    assert view["state"] == "LIVE" and view["paper_pnl"] == "195.00"
    assert view["breakevens"] == ["22326.85", "22873.15"]
    assert [(d["kind"], d["condition"], d["level"], d["index_level"], d["distance_points"], d["distance_percent"],
             d["threshold_percent"], d["price_health"]) for d in view["detections"]] == [
        ("platform_detection", "near_short_strike", "22400.00", "22533.25", "133.25", "0.59", "0.6", "live")]
    async with app_engine.connect() as conn:
        stored_prices = [r[0] for r in await conn.execute(text(
            "SELECT entry_price FROM public.strategy_tracking_legs WHERE strategy_id = :i ORDER BY leg_index"),
            {"i": stored.id})]
    assert stored_prices == [D("39.15"), D("12.95"), D("82.75"), D("35.80")]


async def test_ac1_stale_prices_at_start_are_refused_and_nothing_is_written(app_engine):
    """AC-1/AC-5: ten minutes after the last frame every quote is stale; the start is refused and 0 rows are written."""
    app, stored, _provider, clock, last = await _setup(app_engine)
    clock.now = last + datetime.timedelta(minutes=10)
    async with _client(app) as c:
        refused = await c.post(f"/strategies/{stored.id}/tracking", json={"revision": stored.revision})
    assert refused.status_code == HTTPStatus.CONFLICT and "not live" in refused.text
    assert await _rows(app_engine, stored.id) == (0, 0)


async def test_ac1_a_second_start_a_changed_revision_and_client_prices_are_refused(app_engine):
    """AC-1: one tracking per strategy (409 on the second start, still 1 + 4 rows); a start from another revision is
    refused (409); a body carrying prices is refused (422) - the client never supplies an entry price."""
    app, stored, *_ = await _setup(app_engine)
    async with _client(app) as c:
        forged = await c.post(f"/strategies/{stored.id}/tracking",
                              json={"revision": stored.revision, "legs": [{"entry_price": "1.00"}]})
        assert forged.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        stale_rev = await c.post(f"/strategies/{stored.id}/tracking", json={"revision": stored.revision + 1})
        assert stale_rev.status_code == HTTPStatus.CONFLICT
        assert await _rows(app_engine, stored.id) == (0, 0)
        first = await c.post(f"/strategies/{stored.id}/tracking", json={"revision": stored.revision})
        assert first.status_code == HTTPStatus.CREATED
        again = await c.post(f"/strategies/{stored.id}/tracking", json={"revision": stored.revision})
    assert again.status_code == HTTPStatus.CONFLICT and "already being tracked" in again.text
    assert await _rows(app_engine, stored.id) == (1, 4)


async def test_ac1_another_users_strategy_and_an_untracked_view_answer_not_found(app_engine):
    """AC-1: another user's strategy id answers 404 exactly like a missing one; viewing an untracked strategy is 404."""
    app, stored, *_ = await _setup(app_engine)
    other, _, *_rest = await _setup(app_engine)
    async with _client(other) as c:
        theirs = await c.post(f"/strategies/{stored.id}/tracking", json={"revision": 1})
        assert theirs.status_code == HTTPStatus.NOT_FOUND
    async with _client(app) as c:
        assert (await c.get(f"/strategies/{stored.id}/tracking")).status_code == HTTPStatus.NOT_FOUND
    assert await _rows(app_engine, stored.id) == (0, 0)


async def test_ac1_no_feed_refuses_the_start(app_engine):
    """AC-1 (feed not running): no market context -> 409 'Live prices are not connected', nothing written."""
    app, stored, *_ = await _setup(app_engine, ctx=None)
    async with _client(app) as c:
        refused = await c.post(f"/strategies/{stored.id}/tracking", json={"revision": stored.revision})
    assert refused.status_code == HTTPStatus.CONFLICT and "not connected" in refused.text
    assert await _rows(app_engine, stored.id) == (0, 0)


async def test_ac2_stale_prices_after_start_pause_paper_pnl_and_drop_detection(app_engine):
    """AC-2 / REQ-109 AC-5: after the start, stale prices give state PAUSED, no paper P&L figure, an "as of" time, and
    no detection (the index is not live either)."""
    app, stored, _provider, clock, last = await _setup(app_engine, threshold=D("100"))
    async with _client(app) as c:
        first = await c.post(f"/strategies/{stored.id}/tracking", json={"revision": stored.revision})
        assert first.status_code == HTTPStatus.CREATED
        clock.now = last + datetime.timedelta(minutes=10)
        view = (await c.get(f"/strategies/{stored.id}/tracking")).json()
    assert view["state"] == "PAUSED" and view["paper_pnl"] is None and view["as_of"] is not None
    assert view["detections"] == [] and view["index"]["state"] != "live"


async def test_ac3_a_tracked_strategy_never_reaches_execute(app_engine):
    """AC-3: Execute on a tracked strategy writes no execution plan, and a request carrying a paper entry is refused
    by Execute's own closed body (422)."""
    app, stored, *_ = await _setup(app_engine)
    async with _client(app) as c:
        first = await c.post(f"/strategies/{stored.id}/tracking", json={"revision": stored.revision})
        assert first.status_code == HTTPStatus.CREATED
        paper_body = await c.post(f"/strategies/{stored.id}/execute",
                                  json={"action": "ENTRY", "paper_entry": {"entry_price": "39.15"}})
        assert paper_body.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        plain = await c.post(f"/strategies/{stored.id}/execute", json={"action": "ENTRY"})
    assert plain.status_code >= HTTPStatus.BAD_REQUEST
    async with app_engine.connect() as conn:
        plans = (await conn.execute(text("SELECT count(*) FROM public.execution_plans WHERE strategy_id = :i"),
                                    {"i": stored.id})).scalar_one()
    assert plans == 0


def test_ac3_the_tracking_modules_import_nothing_from_the_order_path():
    """AC-3 (structural): the tracking route, store and domain import no execute/execution/basket module."""
    for path in (ROOT / "backend/ofo_app/routes/tracking.py", ROOT / "backend/ofo_app/tracking_store.py",
                 ROOT / "backend/ofo/tracking/paper.py"):
        imports = [line for line in path.read_text(encoding="utf-8").splitlines()
                   if line.startswith(("import ", "from "))]
        assert not [line for line in imports if "execut" in line or "basket" in line or "orders" in line], path


@pytest.mark.parametrize("threshold", [D("0"), D("101")])
async def test_ac2_a_threshold_setting_outside_0_to_100_fails_closed(app_engine, threshold):
    """AC-2: a broken threshold setting is an error, never a silent default."""
    app, stored, *_ = await _setup(app_engine, threshold=threshold)
    async with _client(app) as c:
        response = await c.post(f"/strategies/{stored.id}/tracking", json={"revision": stored.revision})
    assert response.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR
