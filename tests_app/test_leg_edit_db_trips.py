"""2026-11-06 pool starvation (API pool 2, role limit 5): POST /api/strategies/leg-edit must take at most 2 pooled
connections per request and answer exactly what it answered before. No database: a counting fake sessionmaker stands in
for the pool and the stored reads are fakes; the dependencies under test (state, contract ids, eligibility) are REAL.

Warm = the 60 s state cache (list, today, list-current, freeze limits) is filled; cold = it is empty.
"""
from __future__ import annotations

import asyncio
import types

import pytest
from httpx import ASGITransport, AsyncClient
from ofo.instruments.models import InstrumentId
from ofo_app import catalogue_picker, catalogue_store, db, eligibility_from_zerodha, freeze_read
from ofo_app.main import create_app
from ofo_app.routes import leg_edit
from ofo_app.routes.leg_edit import get_capture
from ofo_app.routes.outcome import (
    get_answer_clock,
    get_margin_source,
    get_market_context,
    load_charge_rates,
)
from ofo_app.routes.planned_entry import get_live_feed
from test_leg_edit_route import CAT, STORED, TODAY, TYPED_STAMP, fake_capture, legs

HTTP_OK = 200
MOVE_WARM_MAX, MOVE_COLD_MAX, STEP_WARM_MAX, STEP_COLD_MAX = 2, 3, 1, 2


class Counter:
    def __init__(self) -> None:
        self.sessions = 0
        self.queries: list[str] = []


class FakeSession:
    counter: Counter | None = None

    async def __aenter__(self):
        FakeSession.counter.sessions += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def connection(self):
        return object()


@pytest.fixture
def counter(monkeypatch):
    c = Counter()
    FakeSession.counter = c
    monkeypatch.setattr(db, "get_sessionmaker", lambda: FakeSession)

    async def load_catalogue(conn):
        c.queries.append("catalogue")
        return CAT

    async def database_today(conn):
        c.queries.append("today")
        return TODAY

    async def list_is_current(conn, today):
        c.queries.append("current")
        return True

    async def limits_in_force(conn):
        c.queries.append("freeze")
        return {}

    async def live_contract_ids(conn, keys):
        c.queries.append("ids")
        return {k: STORED[f"{k.exchange_segment}:{k.exchange_token}"] for k in keys
                if f"{k.exchange_segment}:{k.exchange_token}" in STORED}

    async def live_contract_id(conn, key):  # the pre-fix per-leg query, counted if anything still calls it
        c.queries.append("id")
        return STORED.get(f"{key.exchange_segment}:{key.exchange_token}")

    async def leg_statuses(conn, ids, today):
        c.queries.append("eligibility")
        return [types.SimpleNamespace(tradable=True) for _ in ids]

    monkeypatch.setattr(catalogue_store, "load_catalogue", load_catalogue)
    monkeypatch.setattr(catalogue_picker, "database_today", database_today)
    monkeypatch.setattr(catalogue_picker, "list_is_current", list_is_current)
    monkeypatch.setattr(freeze_read, "limits_in_force", limits_in_force)
    monkeypatch.setattr(catalogue_store, "live_contract_ids", live_contract_ids, raising=False)
    monkeypatch.setattr(catalogue_store, "live_contract_id", live_contract_id)
    monkeypatch.setattr(eligibility_from_zerodha, "leg_statuses", leg_statuses)
    cache = getattr(leg_edit, "_edit_state", None)
    if cache is not None:
        cache.until, cache.value, cache.flight = 0.0, None, None
    else:  # the pre-fix module: its catalogue cache
        leg_edit._catalogue_cache.update(until=0.0, value=None)
    return c


def run(body: dict, times: int = 1):
    app = create_app()
    app.dependency_overrides[get_market_context] = lambda: None
    app.dependency_overrides[get_margin_source] = lambda: None
    app.dependency_overrides[get_live_feed] = lambda: None
    app.dependency_overrides[get_capture] = lambda: fake_capture
    app.dependency_overrides[load_charge_rates] = lambda: None
    app.dependency_overrides[get_answer_clock] = lambda: lambda: TYPED_STAMP

    async def go():
        out = []
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            for _ in range(times):
                r = await client.post("/api/strategies/leg-edit", json={"underlying": "NIFTY"} | body)
                out.append((r.status_code, r.json()))
        return out
    return asyncio.run(go())


STEP = {"legs": legs(), "edit": {"control": "step", "index": 2, "direction": 1}}
SHIFT = {"legs": legs(), "edit": {"control": "shift", "direction": 1}}


def test_step_request_takes_at_most_two_connections_cold_one_warm(counter):
    ((status, _),) = run(STEP)
    assert status == HTTP_OK
    assert counter.sessions <= STEP_COLD_MAX
    before = counter.sessions
    run(STEP)  # warm: the state cache is filled
    assert counter.sessions - before <= STEP_WARM_MAX


def test_shift_request_takes_at_most_two_connections_warm_three_cold(counter):
    ((status, _),) = run(SHIFT)
    assert status == HTTP_OK
    assert counter.sessions <= MOVE_COLD_MAX
    before = counter.sessions
    ((status, _),) = run(SHIFT)
    assert status == HTTP_OK
    assert counter.sessions - before <= MOVE_WARM_MAX


def test_contract_ids_are_one_query_for_all_legs(counter):
    run(STEP)
    assert counter.queries.count("ids") == 1 and counter.queries.count("id") == 0
    assert counter.queries.count("freeze") == 1 and counter.queries.count("catalogue") == 1


def test_state_is_read_once_for_two_requests(counter):
    run(STEP, times=2)
    assert counter.queries.count("today") == 1 and counter.queries.count("current") == 1


def test_contract_lookup_answer_states(counter, monkeypatch):
    """all found / some missing / none: the lookup answers exactly the found ids; a DB error propagates."""
    lookup = leg_edit.get_contract_ids()
    ids = list(STORED)[:3]
    found_all = {InstrumentId(i.split(":")[0], int(i.split(":")[1])): STORED[i] for i in ids}
    answers: dict = {}

    async def fake(conn, keys):
        if answers.get("error"):
            raise RuntimeError("db down")
        wanted = set(keys)
        return {k: v for k, v in answers["rows"].items() if k in wanted}
    monkeypatch.setattr(catalogue_store, "live_contract_ids", fake, raising=False)

    answers["rows"] = found_all
    assert asyncio.run(lookup(ids)) == {i: STORED[i] for i in ids}
    answers["rows"] = dict(list(found_all.items())[:1])
    assert asyncio.run(lookup(ids)) == {ids[0]: STORED[ids[0]]}
    answers["rows"] = {}
    assert asyncio.run(lookup(ids)) == {}
    answers["error"] = True
    with pytest.raises(RuntimeError):
        asyncio.run(lookup(ids))


def test_templates_load_once_per_process(monkeypatch):
    calls = []
    real = leg_edit.load_templates
    monkeypatch.setattr(leg_edit, "load_templates", lambda *a: calls.append(1) or real(*a))
    leg_edit._templates_cache.update(key=None, value=None)
    first = leg_edit.cached_templates()
    assert leg_edit.cached_templates() is first and len(calls) == 1


def test_a_database_error_in_the_state_load_is_raised_and_not_cached(counter, monkeypatch):
    async def boom(conn):
        raise RuntimeError("db down")
    monkeypatch.setattr(catalogue_store, "load_catalogue", boom)
    with pytest.raises(RuntimeError):
        asyncio.run(leg_edit._edit_state_now())
    assert leg_edit._edit_state.value is None
