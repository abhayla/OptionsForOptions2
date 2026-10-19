"""INSTR-FRESH (GC-6, ADR-015 "never uses stale data as if it were live"): Execute refuses to build a basket when the
instrument catalogue was not refreshed from today's Zerodha list (India trading day, judged on the database clock).

The stamp is ``max(last_seen_at)`` of the live Zerodha rows (``elig.list_loaded_at``), written by ``clock_timestamp()``
on every list load, so it needs no new column. The rule: fresh = the stamp falls on the database clock's India date.
Missing, naive (no zone) or later-than-the-clock = not fresh (fail closed). Lot size and expiry come from the stored
catalogue rows (``load_catalogue`` -> ``catalogue.lot_size`` in the gate), so a fresh stamp means they are today's.

No database: the load stamp and the route's other reads are monkeypatched, the real route/gate functions run.
"""
from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest
from ofo.execution import DataHealth, DataInput, ExecutionAction
from ofo_app import eligibility_from_zerodha as elig
from ofo_app.routes import execute as route

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
MON_10_00 = datetime.datetime(2026, 10, 19, 10, 0, tzinfo=IST)  # database clock, Monday
LAST_UPDATE = datetime.datetime(2026, 10, 16, 15, 40, tzinfo=IST)  # Friday's load
TODAY_09_05 = datetime.datetime(2026, 10, 19, 9, 5, tzinfo=IST)


def _install(monkeypatch, loaded) -> None:
    async def _loaded_at(conn):
        return loaded

    monkeypatch.setattr(elig, "list_loaded_at", _loaded_at)


async def _list_state(monkeypatch, loaded, db_now=MON_10_00) -> DataHealth:
    _install(monkeypatch, loaded)
    req = SimpleNamespace(db=None, now=db_now, clock=lambda: db_now,
                          quotes=SimpleNamespace(underlying_price=lambda u: None))
    return (await route._data_health(req, SimpleNamespace(quote_times=()), "NIFTY", db_now))[DataInput.INSTRUMENT_LIST]


async def test_core_a_list_last_loaded_on_friday_is_stale_on_monday_and_a_load_this_morning_passes(monkeypatch):
    assert await _list_state(monkeypatch, LAST_UPDATE) is DataHealth.STALE
    assert await _list_state(monkeypatch, TODAY_09_05) is DataHealth.HEALTHY


@pytest.mark.parametrize("loaded, want", [
    (datetime.datetime(2026, 10, 18, 23, 59, tzinfo=IST), DataHealth.STALE),  # yesterday, a minute before midnight
    (datetime.datetime(2026, 10, 19, 0, 0, tzinfo=IST), DataHealth.HEALTHY),  # today's first instant
    (datetime.datetime(2026, 10, 18, 20, 0, tzinfo=datetime.UTC), DataHealth.HEALTHY),  # 01:30 IST today
    (None, DataHealth.UNAVAILABLE),  # never loaded
    (datetime.datetime(2026, 10, 19, 9, 5), DataHealth.UNAVAILABLE),  # noqa: DTZ001  # naive: zone unknown, never guessed
    (datetime.datetime(2026, 10, 19, 10, 0, 1, tzinfo=IST), DataHealth.STALE),  # later than the clock judging it
    (datetime.datetime(2026, 10, 20, 9, 5, tzinfo=IST), DataHealth.STALE),  # tomorrow
])
def test_the_list_health_rule(loaded, want):
    assert route._list_health(loaded, MON_10_00) is want


def test_a_naive_database_clock_is_never_trusted():
    assert route._list_health(TODAY_09_05, MON_10_00.replace(tzinfo=None)) is DataHealth.UNAVAILABLE


# ---- every basket action reaches the check through the one context builder -----

def _stub_reads(monkeypatch, health_seen: list) -> None:
    async def _margin(req, priced, catalogue):
        return None, None

    async def _none(*a, **k):
        return None

    async def _now(conn):
        return MON_10_00

    async def _data_health(req, priced, underlying, db_now):
        health_seen.append(db_now)
        return dict.fromkeys(DataInput, DataHealth.STALE)

    monkeypatch.setattr(route, "_zerodha_margin", _margin)
    monkeypatch.setattr(route, "_positions", _none)
    monkeypatch.setattr(route, "_pro_entitled", _none)
    monkeypatch.setattr(route, "_reconciliation", lambda *a, **k: frozenset())
    monkeypatch.setattr(route, "_exit_fields", lambda *a, **k: dict(route._NO_ACTIVE_LEGS))
    monkeypatch.setattr(elig, "database_now", _now)
    monkeypatch.setattr(route, "_data_health", _data_health)


@pytest.mark.parametrize("action, want", [("ENTRY", ExecutionAction.NEW_ENTRY), ("EXIT", ExecutionAction.EXIT)])
async def test_entry_and_exit_contexts_carry_the_list_health_judged_on_the_database_clock(monkeypatch, action, want):
    """Dies if ``_context`` stops taking ``data_health`` from ``_data_health`` (the only builder: Complete, Retry and
    adjustments are ENTRY/EXIT baskets through the same ``_execute``)."""
    seen: list = []
    _stub_reads(monkeypatch, seen)
    req = SimpleNamespace(db=None, strategy_id=1, action=action, now=MON_10_00, clock=lambda: MON_10_00)
    definition = SimpleNamespace(underlying="NIFTY", rules_ref=None)
    stored = SimpleNamespace(revision=1, saved=SimpleNamespace(definition=definition))
    held = route._Held({}, _state(action), None, ())
    ctx, _ = await route._context(req, stored, SimpleNamespace(price_bands={}), held, None)
    assert seen == [MON_10_00] and ctx.action is want
    assert all(v is DataHealth.STALE for v in ctx.data_health.values())


def _state(_action):
    from ofo.execution import VersionState  # noqa: PLC0415

    return VersionState.ACTIVE
