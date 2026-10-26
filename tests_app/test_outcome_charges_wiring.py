"""W-075 round 2 (ADR-082 (2)): the outcome route and the live push hand the charge rates in force to the engine.

The rates loader (``ofo_app.routes.outcome.load_charge_rates``) is injected through its cache (``_rates_cache``) or
through a fake session maker: no database, no wall clock (``time.monotonic`` is replaced where the cache expiry is the
subject). Mutants killed: route or push not passing ``rates`` (the sentence stays "before charges and taxes"); the
route passing rates when none is stored.
"""
from __future__ import annotations

import asyncio
import math
import pathlib
import sys
from datetime import date
from decimal import Decimal as D

from httpx import ASGITransport, AsyncClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tests_app"))

from ofo.charges import ChargeRates  # noqa: E402
from ofo_app import charge_rates_store as store  # noqa: E402
from ofo_app import db  # noqa: E402
from ofo_app.main import create_app  # noqa: E402
from ofo_app.routes import outcome  # noqa: E402
from ofo_app.routes.outcome import get_market_context  # noqa: E402
from test_outcome_route import _body, _post, replayed  # noqa: E402,F401
from test_strategy_live_push import ChannelClosed, request, rig, settle  # noqa: E402,F401

HTTP_OK = 200
STORE_READS_AFTER_CACHE_EXPIRY = 2
STORE_READS_AFTER_RETRY = 3

RATES = ChargeRates(
    brokerage_per_order=D("20"), stt_sell_rate=D("0.0015"), stt_exercise_rate=D("0.0015"),
    transaction_rates={"NSE_FO": D("0.0003553"), "BSE_FO": D("0.000325")}, sebi_rate=D("0.000001"),
    stamp_buy_rate=D("0.00003"), gst_rate=D("0.18"), read_on=date(2026, 10, 15), source_url="https://zerodha.com/charges")


def seed(monkeypatch, value):
    monkeypatch.setattr(outcome, "_rates_cache", {"until": math.inf, "value": value})


async def test_route_says_including_charges_when_a_rate_set_is_stored(replayed, monkeypatch):  # noqa: F811 - pytest fixture
    seed(monkeypatch, RATES)
    resp = await _post(_body(replayed), replayed)
    s = resp.json()["summary"]
    assert resp.status_code == HTTP_OK, resp.text
    assert "including about ₹" in s["what_can_i_lose"] and "including about ₹" in s["what_can_i_make"]
    assert s["charges"] is not None and D(s["charges"]) > 0 and s["charges_unavailable"] is False
    assert D(s["max_loss"]) == D("8245.25") + D(s["charges"])


async def test_route_curve_and_totals_are_before_charges_while_max_loss_adds_them(replayed, monkeypatch):  # noqa: F811 - pytest fixture
    seed(monkeypatch, None)
    plain = (await _post(_body(replayed), replayed)).json()
    seed(monkeypatch, RATES)
    body = (await _post(_body(replayed), replayed)).json()
    assert body["payoff"] == plain["payoff"]  # ADR-167 (1): the chart is the engine grid
    assert body["scenario"]["totals"] == plain["scenario"]["totals"]
    assert min(D(t) for t in body["scenario"]["totals"]) == -D("8245.25")
    assert D(body["summary"]["max_loss"]) == D("8245.25") + D(body["summary"]["charges"])  # ADR-167 (3)


async def test_route_keeps_the_old_phrase_when_no_rate_set_is_stored(replayed, monkeypatch):  # noqa: F811 - pytest fixture
    seed(monkeypatch, None)
    s = (await _post(_body(replayed), replayed)).json()["summary"]
    assert s["what_can_i_lose"] == "At most ₹8,245.25 at expiry, before charges and taxes."
    assert s["charges"] is None and s["charges_unavailable"] is True


async def test_live_push_passes_the_rates_and_equals_the_rest_answer(rig, monkeypatch):  # noqa: F811 - pytest fixture
    seed(monkeypatch, RATES)
    provider, feed, channel, _mono, push = rig
    body = request(provider)
    task = asyncio.create_task(push.run())
    await channel.inbound.put(body)
    await settle()
    app = create_app()
    app.dependency_overrides[get_market_context] = lambda: feed.ctx
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        rest = (await ac.post("/api/strategies/outcome", json=body)).json()
    assert "including about ₹" in channel.sent[0]["summary"]["what_can_i_lose"]
    assert channel.sent[0] == rest
    await channel.inbound.put(ChannelClosed)
    await task


async def test_live_push_without_a_rate_set_keeps_the_old_phrase(rig, monkeypatch):  # noqa: F811 - pytest fixture
    seed(monkeypatch, None)
    provider, _feed, channel, _mono, push = rig
    task = asyncio.create_task(push.run())
    await channel.inbound.put(request(provider))
    await settle()
    assert channel.sent[0]["summary"]["what_can_i_lose"].endswith("before charges and taxes.")
    await channel.inbound.put(ChannelClosed)
    await task


class _FakeSession:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return False


async def test_loader_reads_the_store_caches_300s_and_retries_a_failure_after_30s(monkeypatch):
    clock = {"now": 100.0}
    calls = []
    outcomes = [RATES, RuntimeError("db down"), RATES]

    async def fake_rates_in_force(session):
        calls.append(clock["now"])
        out = outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out

    monkeypatch.setattr(outcome.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(db, "get_sessionmaker", lambda: _FakeSession)
    monkeypatch.setattr(store, "rates_in_force", fake_rates_in_force)
    monkeypatch.setattr(outcome, "_rates_cache", {"until": 0.0, "value": None})

    assert await outcome.load_charge_rates() is RATES
    clock["now"] = 399.0  # inside the 300 s window: no second read
    assert await outcome.load_charge_rates() is RATES and len(calls) == 1
    clock["now"] = 401.0  # expired: a read that fails gives None, not an error
    assert await outcome.load_charge_rates() is None and len(calls) == STORE_READS_AFTER_CACHE_EXPIRY
    clock["now"] = 420.0  # inside the 30 s failure window: still None, no read
    assert await outcome.load_charge_rates() is None and len(calls) == STORE_READS_AFTER_CACHE_EXPIRY
    clock["now"] = 432.0  # failure window over: read again
    assert await outcome.load_charge_rates() is RATES and len(calls) == STORE_READS_AFTER_RETRY


async def test_concurrent_callers_after_expiry_trigger_one_load(monkeypatch):
    """GC-6: 20 concurrent callers at TTL expiry open exactly ONE session; a failed load is remembered for 30 s."""
    opened = []

    class _Slow:
        async def __aenter__(self):
            opened.append(1)
            await asyncio.sleep(0.05)
            return object()

        async def __aexit__(self, *exc):
            return False

    async def rates(session):
        return RATES

    monkeypatch.setattr(db, "get_sessionmaker", lambda: _Slow)
    monkeypatch.setattr(store, "rates_in_force", rates)
    monkeypatch.setattr(outcome, "_rates_cache", {"until": 0.0, "value": None})
    got = await asyncio.gather(*(outcome.load_charge_rates() for _ in range(20)))
    assert got == [RATES] * 20 and len(opened) == 1

    async def broken(session):
        raise RuntimeError("down")

    opened.clear()
    monkeypatch.setattr(store, "rates_in_force", broken)
    monkeypatch.setattr(outcome, "_rates_cache", {"until": 0.0, "value": None})
    got = await asyncio.gather(*(outcome.load_charge_rates() for _ in range(20)))
    assert got == [None] * 20 and len(opened) == 1
    assert await outcome.load_charge_rates() is None and len(opened) == 1  # remembered: no new session


async def test_a_cancelled_caller_does_not_cancel_the_shared_load(monkeypatch):
    """The load is shielded: cancel one waiting caller mid-load, the others still get the rates (one session)."""
    opened = []
    release = asyncio.Event()

    class _Held:
        async def __aenter__(self):
            opened.append(1)
            await release.wait()
            return object()

        async def __aexit__(self, *exc):
            return False

    async def rates(session):
        return RATES

    monkeypatch.setattr(db, "get_sessionmaker", lambda: _Held)
    monkeypatch.setattr(store, "rates_in_force", rates)
    monkeypatch.setattr(outcome, "_rates_cache", {"until": 0.0, "value": None})
    tasks = [asyncio.create_task(outcome.load_charge_rates()) for _ in range(3)]
    await asyncio.sleep(0.01)  # all three are waiting on the one load
    tasks[0].cancel()
    await asyncio.sleep(0.01)
    release.set()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    assert isinstance(results[0], asyncio.CancelledError)
    assert results[1:] == [RATES, RATES] and len(opened) == 1
