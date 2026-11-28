"""Gap 2 of the 27 Nov live test day (Lane Q2): ONE price read is slow and the screens must not pay for it.

Real case 27 Nov (PC): a Kite quote read stalled while the feed's ticks were fresh; the pages that waited on it held the
API's 2 database connections, so /health and the strategies list stopped answering, and screens said "not live" though
the feed was live. Here the feed is the scenario's (fresh ticks); the REST index quote is the one slow read.

Three claims, each a test:
 (1) while 3 plan-watch requests wait on the stalled read, /health and the strategies list still answer (the pool of 2
     is not held by a read that is waiting on the market);
 (2) a 5 s stalled read: the plan-watch answer does not say "not live" (no paused line, no `now` missing) when the
     feed has fresh ticks (REQ-049 AC-4 says "not live" only when the data is);
 (3) a rate-limited (HTTP 429) quote never turns live ticks into "not live", on plan-watch and on the adjustment check.
No timing is asserted: probes are bounded with ``wait_for`` (a regression raises TimeoutError instead of hanging).
Spec basis: REQ-049 AC-4, ADR-212, ADR-330 (39), REQ-119 AC-4. Fixes: origin/hotfix/api-blocking-1127 (the pool),
origin/hotfix/plan-watch-load-1127 (the budget on the stalled read).
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from ofo.marketdata.spot_source import SourceReading, SourceState
from ofo_app import db as app_db
from ofo_app import live_market
from ofo_app.routes import paper
from ofo_app.routes.adjustment import get_market_reader, get_rest_spot_reader
from ofo_app.routes.planned_entry import get_live_feed
from test_adjustment_check import (
    _reset_engine,
    _seeded,
    app_db_url,  # noqa: F401 - the fixture of the check tests
)

OK = 200
STALLED_REQUESTS = 3  # one more than the API pool (DB_POOL_SIZE 2, no overflow)
PROBE_BOUND_S = 8  # a probe that is not answered by then is a failure, not a slow answer
STALL_S = 5
BAD_STATES = ("paused",)


def _app():
    from ofo_app.main import create_app  # noqa: PLC0415 - the env must be set first
    _reset_engine()
    return create_app()


class Stalled:
    """A REST quote reader that waits for ``gate`` (or STALL_S) and counts the callers that entered it."""

    def __init__(self, *, seconds: float | None = None):
        self.gate, self.entered, self.seconds = asyncio.Event(), 0, seconds

    async def __call__(self, *_args) -> SourceReading:
        self.entered += 1
        if self.seconds is not None:
            await asyncio.sleep(self.seconds)
        else:
            await self.gate.wait()
        if len(_args) == 2:  # noqa: PLR2004 - the market reader's (tracked, ctx): it has nothing to return when cut
            raise TimeoutError("the stalled market read was released")
        return SourceReading(SourceState.FAILED)


async def _until(done) -> None:
    while not done():  # noqa: ASYNC110 - a counter another task moves; bounded by the caller's wait_for
        await asyncio.sleep(0.01)


async def _entered(reader: Stalled, count: int) -> None:
    await _until(lambda: reader.entered >= count)


@pytest.mark.parametrize("route", ["plan-watch", "adjustment-check"])
@pytest.mark.parametrize("dep", [get_rest_spot_reader, get_market_reader], ids=["rest_quote", "market_read"])
async def test_plan_watch_and_check_do_not_hold_the_pool_while_a_read_stalls(
        app_db_url, monkeypatch, route, dep):  # noqa: F811
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    if dep is get_rest_spot_reader:
        # FD3 item 6: the scenario's frame is a USABLE feed tick at the scenario's own clock, and a usable feed answers
        # the spot with no REST call (``index_spot_of`` (1), ADR-330 (39)), so the REST reader was never reached and the
        # test proved nothing (test out of step, not a defect). The feed here has NO usable tick on the first pass:
        # the REST reader is then read, which is the stall this test measures.
        from ofo_app.routes import outcome  # noqa: PLC0415
        real_resolve = outcome.resolve_spot

        def feed_has_no_tick_first(feed, rest, last_close, **kwargs):
            if rest is None and last_close is None:  # index_spot_of's first pass: the feed alone
                feed = SourceReading(SourceState.ABSENT)
            return real_resolve(feed, rest, last_close, **kwargs)
        monkeypatch.setattr(outcome, "resolve_spot", feed_has_no_tick_first)
    reader, app = Stalled(), _app()
    app.dependency_overrides[dep] = lambda: reader
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        stalled = [asyncio.create_task(ac.get(f"/api/strategies/{sid}/{route}"))
                   for _ in range(STALLED_REQUESTS)]
        try:
            await asyncio.wait_for(_entered(reader, STALLED_REQUESTS), PROBE_BOUND_S)
            health = await asyncio.wait_for(ac.get("/health"), PROBE_BOUND_S)
            listing = await asyncio.wait_for(ac.get("/" + "strategies"), PROBE_BOUND_S)
        finally:
            reader.gate.set()
            await asyncio.gather(*stalled, return_exceptions=True)
    await app_db.close_db()
    assert (health.status_code, listing.status_code) == (OK, OK), (health.text, listing.text)


@pytest.mark.parametrize("path", ["/paper/strategies/{sid}", "/paper/strategies"])
async def test_other_routes_answer_while_paper_reads_wait_on_a_stalled_price(app_db_url, monkeypatch, path):  # noqa: F811
    """The 27 Nov hold: a paper read waits for the feed's ready price (``_hold_until_ready``). The wait is one stalled
    read here (a gate); 3 requests wait on it against the pool of 2, and /health and the strategies list must answer."""
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    gate, entered = asyncio.Event(), []

    async def stalled(_feed, _ctx, underlying, _ids, snapshot):
        entered.append(underlying)
        await gate.wait()
        return snapshot

    monkeypatch.setattr(paper, "_hold_until_ready", stalled)
    monkeypatch.setattr(paper, "_read_ready", lambda _snapshot, _ids: False)  # an unready read: the hold is taken
    app = _app()
    app.dependency_overrides[get_live_feed] = lambda: SimpleNamespace(fanout=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        tasks = [asyncio.create_task(ac.get(path.format(sid=sid))) for _ in range(STALLED_REQUESTS)]
        try:
            await asyncio.wait_for(_until(lambda: len(entered) >= STALLED_REQUESTS), PROBE_BOUND_S)
            health = await asyncio.wait_for(ac.get("/health"), PROBE_BOUND_S)
            listing = await asyncio.wait_for(ac.get("/" + "strategies"), PROBE_BOUND_S)
        finally:
            gate.set()
            await asyncio.gather(*tasks, return_exceptions=True)
    await app_db.close_db()
    assert (health.status_code, listing.status_code) == (OK, OK), (health.text, listing.text)


def _says_not_live(out: dict) -> list:
    return [x for x in out["lines"] if x["state"] in BAD_STATES] + ([out["paused"]] if out.get("paused") else [])


async def test_a_5_second_stalled_quote_does_not_make_live_ticks_not_live(app_db_url, monkeypatch):  # noqa: F811
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    app = _app()
    app.dependency_overrides[get_rest_spot_reader] = lambda: Stalled(seconds=STALL_S)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        # the screen's own wait is shorter than the stall: the answer must come inside it, with live figures
        r = await asyncio.wait_for(ac.get(f"/api/strategies/{sid}/plan-watch"), STALL_S - 0.2)
    await app_db.close_db()
    out = r.json()
    assert r.status_code == OK, out
    assert _says_not_live(out) == [], _says_not_live(out)
    assert any(x["now"] is not None for x in out["lines"]), out["lines"]


RATE_LIMITED = (429, json.dumps({"status": "error", "message": "Too many requests", "error_type": "NetworkException"}))


async def _rate_limited(_underlying: str) -> SourceReading:
    return await live_market.index_spot("NIFTY", RATE_LIMITED)


async def test_a_429_quote_is_a_failed_read_not_a_value(app_db_url):  # noqa: F811
    reading = await _rate_limited("NIFTY")
    assert reading.state is SourceState.FAILED and reading.value is None


@pytest.mark.parametrize("route", ["plan-watch", "adjustment-check"])
async def test_a_429_broker_quote_never_turns_live_ticks_into_not_live(app_db_url, monkeypatch, route):  # noqa: F811
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    app = _app()
    app.dependency_overrides[get_rest_spot_reader] = lambda: _rate_limited
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await asyncio.wait_for(ac.get(f"/api/strategies/{sid}/{route}"), PROBE_BOUND_S)
    await app_db.close_db()
    out = r.json()
    assert r.status_code == OK, out
    if route == "plan-watch":
        assert _says_not_live(out) == [] and any(x["now"] is not None for x in out["lines"]), out["lines"]
    else:
        assert not out.get("paused"), out.get("paused")
        assert out["results"], out  # the plan was evaluated on the live ticks
