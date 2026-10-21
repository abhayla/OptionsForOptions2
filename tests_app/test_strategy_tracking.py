"""W-122 over HTTP on the recorded replay (REQ-109 AC-1, AC-2; the detection numbers are REQ-045 AC-2, W-123).

The saved strategy is test_strategy_store's iron condor (65 units a leg, expiry 2026-10-13): SELL 22800 CE,
BUY 23000 CE, SELL 22400 PE, BUY 22200 PE. The market is the real 2026-10-08 recording (tests/fixtures/kite_ws)
valued at its last frame 09:20:09 IST, NIFTY 50 at 22,533.25; the recorded LTPs there are 39.15, 12.95, 82.75 and 35.80.
"""
from __future__ import annotations

import contextlib
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
from ofo_app import tracked_contracts  # noqa: E402
from ofo_app.routes import tracking as tracking_routes  # noqa: E402
from ofo_app.routes.outcome import MarketContext, get_answer_clock, get_market_context  # noqa: E402
from ofo_app.routes.planned_entry import get_live_feed  # noqa: E402
from test_strategy_store import WING, _app, _body, _client, _ids, _user, _with_draft  # noqa: E402

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


@pytest.fixture
async def db(app_engine):
    """One connection whose outer transaction is always rolled back: the route's commits become savepoints, so no
    test leaves a row in the insert-only tracking tables (finding branch-migration-tests-move-shared-db)."""
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


@contextlib.asynccontextmanager
async def _same(conn):
    yield conn


async def _setup(db, *, ctx="replay", threshold=THRESHOLD):
    user = _user()
    _, stored = await _with_draft(db, user)
    provider, clock, last = _market()
    maker = async_sessionmaker(bind=db, class_=AsyncSession, expire_on_commit=False,
                               join_transaction_mode="create_savepoint")
    app = _app(maker, user)
    context = MarketContext(provider, lambda: last, D("0.065")) if ctx == "replay" else None
    app.dependency_overrides[get_market_context] = lambda: context
    app.dependency_overrides[get_live_feed] = lambda: None
    app.dependency_overrides[get_answer_clock] = lambda: lambda: ANSWERED
    app.dependency_overrides[tracking_routes.get_near_level_threshold] = lambda: threshold
    return app, stored, provider, clock, last


async def _rows(db, strategy_id: int) -> tuple[int, int]:
    a = (await db.execute(text("SELECT count(*) FROM public.strategy_tracking WHERE strategy_id = :i"),
                          {"i": strategy_id})).scalar_one()
    b = (await db.execute(text("SELECT count(*) FROM public.strategy_tracking_legs WHERE strategy_id = :i"),
                          {"i": strategy_id})).scalar_one()
    return int(a), int(b)


async def test_ac1_ac2_core_proof_start_stores_entry_and_view_gives_paper_pnl_and_one_detection(db):
    """AC-1/AC-2 core proof (REQ-045 AC-1/AC-2 too). Start stores the recorded LTPs 39.15 / 12.95 / 82.75 / 35.80 as
    the entry. The feed then moves the legs to 45.15 / 14.95 / 70.75 / 30.80. By hand: (39.15 - 45.15) x 65 = -390.00;
    (14.95 - 12.95) x 65 = +130.00; (82.75 - 70.75) x 65 = +780.00; (30.80 - 35.80) x 65 = -325.00 -> +195.00.
    Threshold 0.6: short strike 22400 vs 22533.25 = 133.25 points = 133.25 / 22533.25 x 100 = 0.5913 -> 0.59% fires,
    labelled 'Adjustment opportunity detected'; 22800 (1.18%) and the breakevens 22326.85 (0.92%) / 22873.15 (1.51%)
    do not (credit 73.15 = 39.15 - 12.95 + 82.75 - 35.80)."""
    app, stored, provider, _clock, last = await _setup(db)
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
    async with _same(db) as conn:
        stored_prices = [r[0] for r in await conn.execute(text(
            "SELECT entry_price FROM public.strategy_tracking_legs WHERE strategy_id = :i ORDER BY leg_index"),
            {"i": stored.id})]
    assert stored_prices == [D("39.15"), D("12.95"), D("82.75"), D("35.80")]


def _quantity_130(body: dict) -> dict:
    body["legs"][0]["quantity"] = 130
    return body


def _three_legs(body: dict) -> dict:
    body["legs"] = body["legs"][:3]
    return body


@pytest.mark.parametrize(("edit", "wing"), [(_quantity_130, "NIFTY26O1323000CE"), (lambda b: b, WING),
                                            (_three_legs, "NIFTY26O1323000CE")],
                         ids=["quantity", "strike", "leg_count"])
async def test_ac2_an_edit_after_the_start_changes_nothing_in_the_tracked_figures(db, edit, wing):
    """AC-2 ("from the paper entry prices"): after the start, the saved strategy is edited (PUT 200): leg 1 quantity
    65 -> 130, or the BUY 23000 CE wing moved to 23100 CE, or the last leg removed. The view still reads the stored
    paper entry only: the same four legs (65 units each, 23000 CE wing), the same +195.00 by hand
    ((39.15 - 45.15) x 65 + (14.95 - 12.95) x 65 + (82.75 - 70.75) x 65 + (30.80 - 35.80) x 65
    = -390 + 130 + 780 - 325),
    the same breakevens 22326.85 / 22873.15 and the same 22400 detection (133.25 points, 0.59%)."""
    app, stored, provider, _clock, last = await _setup(db)
    ids = await _ids(db)
    async with _client(app) as c:
        first = await c.post(f"/strategies/{stored.id}/tracking", json={"revision": stored.revision})
        assert first.status_code == HTTPStatus.CREATED
        edited = await c.put(f"/strategies/{stored.id}",
                             json=edit(_body(ids, wing=wing, expected_revision=stored.revision)))
        assert edited.status_code == HTTPStatus.OK, edited.text
        for iid, rupees in zip(IDS, ["45.15", "14.95", "70.75", "30.80"], strict=True):
            provider.on_frame(_frame(provider, iid, rupees), last)
        view = (await c.get(f"/strategies/{stored.id}/tracking")).json()
    assert [(leg["instrument_id"], leg["action"], leg["quantity"], leg["entry_price"]) for leg in view["legs"]] == [
        ("NSE_FO:44624", "SELL", 65, "39.15"), ("NSE_FO:44632", "BUY", 65, "12.95"),
        ("NSE_FO:44604", "SELL", 65, "82.75"), ("NSE_FO:44595", "BUY", 65, "35.80")]
    assert view["state"] == "LIVE" and view["paper_pnl"] == "195.00"
    assert view["breakevens"] == ["22326.85", "22873.15"]
    assert [(d["level"], d["distance_points"], d["distance_percent"]) for d in view["detections"]] == [
        ("22400.00", "133.25", "0.59")]


async def test_ac1_stale_prices_at_start_are_refused_and_nothing_is_written(db):
    """AC-1/AC-5: ten minutes after the last frame every quote is stale; the start is refused and 0 rows are written."""
    app, stored, _provider, clock, last = await _setup(db)
    clock.now = last + datetime.timedelta(minutes=10)
    async with _client(app) as c:
        refused = await c.post(f"/strategies/{stored.id}/tracking", json={"revision": stored.revision})
    assert refused.status_code == HTTPStatus.CONFLICT and "not live" in refused.text
    assert await _rows(db, stored.id) == (0, 0)


async def test_ac1_a_second_start_a_changed_revision_and_client_prices_are_refused(db):
    """AC-1: one tracking per strategy (409 on the second start, still 1 + 4 rows); a start from another revision is
    refused (409); a body carrying prices is refused (422) - the client never supplies an entry price."""
    app, stored, *_ = await _setup(db)
    async with _client(app) as c:
        forged = await c.post(f"/strategies/{stored.id}/tracking",
                              json={"revision": stored.revision, "legs": [{"entry_price": "1.00"}]})
        assert forged.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        stale_rev = await c.post(f"/strategies/{stored.id}/tracking", json={"revision": stored.revision + 1})
        assert stale_rev.status_code == HTTPStatus.CONFLICT
        assert await _rows(db, stored.id) == (0, 0)
        first = await c.post(f"/strategies/{stored.id}/tracking", json={"revision": stored.revision})
        assert first.status_code == HTTPStatus.CREATED
        again = await c.post(f"/strategies/{stored.id}/tracking", json={"revision": stored.revision})
    assert again.status_code == HTTPStatus.CONFLICT and "already being tracked" in again.text
    assert await _rows(db, stored.id) == (1, 4)


async def test_ac1_a_second_start_is_refused_as_already_tracked_before_any_price_read(db):
    """AC-1: the route checks "already tracked" before it reads prices, so a second start while prices are stale still
    says the strategy is already being tracked (not "prices not live") and writes nothing."""
    app, stored, _provider, clock, last = await _setup(db)
    async with _client(app) as c:
        first = await c.post(f"/strategies/{stored.id}/tracking", json={"revision": stored.revision})
        assert first.status_code == HTTPStatus.CREATED
        clock.now = last + datetime.timedelta(minutes=10)
        again = await c.post(f"/strategies/{stored.id}/tracking", json={"revision": stored.revision})
    assert again.status_code == HTTPStatus.CONFLICT and "already being tracked" in again.text
    assert await _rows(db, stored.id) == (1, 4)


async def test_ac1_the_store_refuses_a_second_entry_even_without_the_route_check(db):
    """AC-1: the store itself refuses a second start (ALREADY_TRACKED; the route's pre-check is a second layer), so a
    race past the route check still leaves exactly 1 + 4 rows."""
    _app, stored, provider, _clock, last = await _setup(db)
    from ofo.outcome import read_snapshot  # noqa: PLC0415
    from ofo.tracking import paper  # noqa: PLC0415
    from ofo_app import strategy_store as store  # noqa: PLC0415
    from ofo_app import tracking_store  # noqa: PLC0415

    legs = [paper.TrackedLeg(i, leg.action, leg.instrument, leg.strike, leg.expiry, leg.quantity, D(0), last)
            for i, leg in zip(IDS, stored.saved.definition.legs, strict=True)]
    entry = paper.capture_entry(read_snapshot(provider, "NIFTY", IDS, last, D("0.065")), legs)
    user = stored.user_ref
    async with _same(db) as conn:
        await tracking_store.start(conn, user, stored.id, stored.revision, stored.saved.contract_ids, entry)
        with pytest.raises(store.StrategyStoreError) as refused:
            await tracking_store.start(conn, user, stored.id, stored.revision, stored.saved.contract_ids, entry)
        assert refused.value.code == tracking_store.ALREADY_TRACKED
    assert await _rows(db, stored.id) == (1, 4)


async def test_ac1_another_users_strategy_and_an_untracked_view_answer_not_found(db):
    """AC-1: another user's strategy id answers 404 exactly like a missing one; viewing an untracked strategy is 404."""
    app, stored, *_ = await _setup(db)
    other, _, *_rest = await _setup(db)
    async with _client(other) as c:
        theirs = await c.post(f"/strategies/{stored.id}/tracking", json={"revision": 1})
        assert theirs.status_code == HTTPStatus.NOT_FOUND
    async with _client(app) as c:
        assert (await c.get(f"/strategies/{stored.id}/tracking")).status_code == HTTPStatus.NOT_FOUND
    assert await _rows(db, stored.id) == (0, 0)


async def test_ac1_no_feed_refuses_the_start(db):
    """AC-1 (feed not running): no market context -> 409 'Live prices are not connected', nothing written."""
    app, stored, *_ = await _setup(db, ctx=None)
    async with _client(app) as c:
        refused = await c.post(f"/strategies/{stored.id}/tracking", json={"revision": stored.revision})
    assert refused.status_code == HTTPStatus.CONFLICT and "not connected" in refused.text
    assert await _rows(db, stored.id) == (0, 0)


async def test_ac2_stale_prices_after_start_pause_paper_pnl_and_drop_detection(db):
    """AC-2 / REQ-109 AC-5: after the start, stale prices give state PAUSED, no paper P&L figure, an "as of" time, and
    no detection (the index is not live either)."""
    app, stored, _provider, clock, last = await _setup(db, threshold=D("100"))
    async with _client(app) as c:
        first = await c.post(f"/strategies/{stored.id}/tracking", json={"revision": stored.revision})
        assert first.status_code == HTTPStatus.CREATED
        clock.now = last + datetime.timedelta(minutes=10)
        view = (await c.get(f"/strategies/{stored.id}/tracking")).json()
    assert view["state"] == "PAUSED" and view["paper_pnl"] is None and view["as_of"] is not None
    assert view["detections"] == [] and view["index"]["state"] != "live"


async def test_ac1_a_tracked_strategy_never_reaches_execute(db):
    """AC-1 (order path off; REQ-109 AC-3 itself is Step 5): Execute on a tracked strategy writes no execution
    plan, and a request carrying a paper entry is refused: by W-121's order-path switch, which runs first while the
    order path is off (409), or else by Execute's own closed body (422)."""
    app, stored, *_ = await _setup(db)
    async with _client(app) as c:
        first = await c.post(f"/strategies/{stored.id}/tracking", json={"revision": stored.revision})
        assert first.status_code == HTTPStatus.CREATED
        paper_body = await c.post(f"/strategies/{stored.id}/execute",
                                  json={"action": "ENTRY", "paper_entry": {"entry_price": "39.15"}})
        assert paper_body.status_code in {HTTPStatus.CONFLICT, HTTPStatus.UNPROCESSABLE_ENTITY}
        plain = await c.post(f"/strategies/{stored.id}/execute", json={"action": "ENTRY"})
    assert plain.status_code >= HTTPStatus.BAD_REQUEST
    async with _same(db) as conn:
        plans = (await conn.execute(text("SELECT count(*) FROM public.execution_plans WHERE strategy_id = :i"),
                                    {"i": stored.id})).scalar_one()
    assert plans == 0


@pytest.mark.parametrize("threshold", [D("0"), D("101")])
async def test_ac2_a_threshold_setting_outside_0_to_100_fails_closed(db, threshold):
    """AC-2: a broken threshold setting is an error, never a silent default."""
    app, stored, *_ = await _setup(db, threshold=threshold)
    async with _client(app) as c:
        response = await c.post(f"/strategies/{stored.id}/tracking", json={"revision": stored.revision})
    assert response.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR


# --- Round 3 (independent redesign): a stored contract id is priced only while it is live AND still holds its own
# exchange token (ofo_app.tracked_contracts). The catalogue answer states: live, retired, delisted, token reassigned,
# contract row missing. Leg 0 is SELL 22800 CE on NSE_FO:44624 (expiry 2026-10-13, before today, so it may retire).

_DELIST = "UPDATE public.catalogue_contracts SET delisted = TRUE, currently_listed = FALSE WHERE id = :id"
_RETIRE = "UPDATE public.catalogue_contracts SET retired = TRUE, currently_listed = FALSE WHERE id = :id"
_REUSE = ("INSERT INTO public.catalogue_contracts (exchange_segment, exchange_token, name, expiry, strike, "
          "instrument_type) VALUES ('NSE_FO', 44624, 'NIFTY', DATE '2026-11-24', 26000, 'CE')")


async def _started_then(db, *sqls: str):
    """Start tracking (entry 39.15 / 12.95 / 82.75 / 35.80), run ``sqls`` on leg 0's contract, move the feed to the
    core proof's 45.15 / 14.95 / 70.75 / 30.80 (so an unchecked view would answer LIVE +195.00), and view."""
    app, stored, provider, _clock, last = await _setup(db, threshold=D("100"))
    async with _client(app) as c:
        started = await c.post(f"/strategies/{stored.id}/tracking", json={"revision": stored.revision})
        assert started.status_code == HTTPStatus.CREATED, started.text
        for sql in sqls:
            await db.execute(text(sql), {"id": stored.saved.contract_ids[0]})
        for iid, rupees in zip(IDS, ["45.15", "14.95", "70.75", "30.80"], strict=True):
            provider.on_frame(_frame(provider, iid, rupees), last)
        view = await c.get(f"/strategies/{stored.id}/tracking")
    assert view.status_code == HTTPStatus.OK, view.text
    return view.json()


def _assert_paused_by(view: dict, reason: str) -> None:
    assert (view["state"], view["pause_reason"], view["paper_pnl"], view["detections"]) == ("PAUSED", reason, None, [])
    leg0 = view["legs"][0]
    assert (leg0["price_state"], leg0["current_price"], leg0["strike"], leg0["entry_price"]) == (
        reason, None, "22800.00", "39.15")
    assert [leg["price_state"] for leg in view["legs"][1:]] == ["live", "live", "live"]


async def test_ac2_a_reused_token_never_prices_the_tracked_leg_token_reassigned(db):
    """The round-2 verifier's case: leg 0's contract is delisted and a NEW live contract (26000 CE, 2026-11-24) takes
    its token NSE_FO:44624, whose quote is 45.15. The view is PAUSED for token_reassigned, with no paper P&L figure
    (never +195.00 from another contract's price) and no detection, though threshold 100 would fire on any level."""
    _assert_paused_by(await _started_then(db, _DELIST, _REUSE), "token_reassigned")


async def test_ac2_a_retired_leg_pauses_the_view_contract_retired(db):
    """A leg whose contract retired after its expiry (ADR-057): PAUSED contract_retired (settlement is AC-7, Step 5)."""
    _assert_paused_by(await _started_then(db, _RETIRE), "contract_retired")


async def test_ac2_a_delisted_leg_whose_token_is_not_reused_pauses_contract_delisted(db):
    """A delisted leg (ADR-058) whose token no live contract holds: PAUSED contract_delisted, though the feed still
    quotes NSE_FO:44624."""
    _assert_paused_by(await _started_then(db, _DELIST), "contract_delisted")


@pytest.mark.parametrize(("sqls", "state"), [((_DELIST, _REUSE), "token_reassigned"), ((_RETIRE,), "contract_retired"),
                                             ((_DELIST,), "contract_delisted")])
async def test_ac1_start_is_refused_for_a_leg_not_live_and_nothing_is_written(db, sqls, state):
    """AC-1: Start tracking refuses the same states (409 tracking_contract_not_live, 0 rows), before any price read."""
    app, stored, *_ = await _setup(db)
    for sql in sqls:
        await db.execute(text(sql), {"id": stored.saved.contract_ids[0]})
    found = await tracked_contracts.resolve_one(db, stored.saved.contract_ids[0])
    assert (found.state, found.feed_key) == (state, None)
    async with _client(app) as c:
        refused = await c.post(f"/strategies/{stored.id}/tracking", json={"revision": stored.revision})
    assert refused.status_code == HTTPStatus.CONFLICT and "no longer a live contract" in refused.text
    assert await _rows(db, stored.id) == (0, 0)


async def test_the_catalogue_answer_states_live_and_contract_row_missing(db):
    """The helper's other two states: a live contract holding its own token gives its feed key; an id no stored
    contract has is contract_missing (no key, fails closed)."""
    _app, stored, *_ = await _setup(db)
    live = await tracked_contracts.resolve(db, stored.saved.contract_ids)
    assert [(c.state, c.feed_key) for c in live] == [("live", iid) for iid in IDS]
    missing = await tracked_contracts.resolve_one(db, 2**62)
    assert (missing.state, missing.feed_key, missing.stored) == ("contract_missing", None, None)
