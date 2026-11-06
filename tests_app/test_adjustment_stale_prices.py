"""ADR-272 (issues 79, 87, 77, 91): the Compare/approaches reply names the age of its prices; stale prices rank nothing.

Real scenario library data (ADJ-02 iron condor); only the freshness seam of the market is varied.
"""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from ofo.adjustment import approaches as ap
from ofo.adjustment.approaches import Position, PositionLeg
from ofo.rules.inputs import DataHealth
from ofo.timeutil import IST
from ofo_app import adjustment_check as check
from ofo_app import adjustment_readers as readers
from ofo_app.routes import adjustment as route
from test_adjustment_approaches_route import RATES, client_for, load, market_of, post


def _reply(*, stale: bool, at_minutes_old: int | None):
    sc = load("ADJ-02")
    c = client_for(sc, rates=RATES)
    now = datetime.datetime.fromisoformat(sc["clock"]["ist"])
    at = None if at_minutes_old is None else now - datetime.timedelta(minutes=at_minutes_old)

    async def market(_t, _ctx):
        return dataclasses.replace(market_of(sc), prices_stale=stale, prices_at=at)
    c.app.dependency_overrides[route.get_market_reader] = lambda: market
    return post(c).json(), now


def test_fresh_prices_say_so_and_still_rank():
    body, _ = _reply(stale=False, at_minutes_old=0)
    p = body["prices"]
    assert p["stale"] is False and p["banner"] is None and p["prepare_blocked_reason"] is None
    assert p["label"].startswith("prices from ") and p["label"].endswith(("AM", "PM"))  # ADR-015 clock form
    assert any(c["leaders"] for c in body["criteria"])


def test_stale_prices_carry_age_and_as_of_and_rank_nothing():
    body, now = _reply(stale=True, at_minutes_old=10)
    p = body["prices"]
    last = (now - datetime.timedelta(minutes=10)).astimezone(IST)
    assert p["stale"] is True and p["age_minutes"] == 10  # noqa: PLR2004 - the minutes set above
    assert p["banner"] == f"Prices are 10 min old (last update {last:%H:%M} IST): figures below are not live."
    assert p["as_of_note"] == f"as of {last:%H:%M}"
    assert p["prepare_blocked_reason"] == "Wait for fresh prices"
    assert body["criteria"] and all(c["leaders"] == [] for c in body["criteria"])
    assert all(v == {"n": 0, "m": 0} for v in body["leads"].values())


def test_stale_with_no_timestamp_is_stale_with_no_age():
    body, _ = _reply(stale=True, at_minutes_old=None)
    p = body["prices"]
    assert p["stale"] is True and p["age_minutes"] is None and p["as_of"] is None
    assert p["banner"] == "Prices are not live (no recent update): figures below are not live."
    assert all(c["leaders"] == [] for c in body["criteria"])


# every answer state of the freshness input, at the reader
NOW = datetime.datetime(2026, 11, 5, 10, 0, tzinfo=IST)
LEG = PositionLeg("SELL", "CE", D("23400"), datetime.date(2026, 11, 10), 1, D("100"), "NIFTY26N1023400CE")
LEG2 = PositionLeg("SELL", "PE", D("22600"), datetime.date(2026, 11, 10), 1, D("100"), "NIFTY26N1022600PE")
POS = Position("NIFTY", 75, "weekly", NOW.date(), (LEG, LEG2))
IDS = {LEG.tradingsymbol: "a", LEG2.tradingsymbol: "b"}


def _ctx(health: str | None):
    status = SimpleNamespace(health=SimpleNamespace(value=health))
    return SimpleNamespace(provider=SimpleNamespace(status=lambda: status))


def _q(minutes_old: int, health=DataHealth.AVAILABLE):
    return SimpleNamespace(timestamp=NOW - datetime.timedelta(minutes=minutes_old), health=health)


@pytest.mark.parametrize(("name", "ctx", "quotes", "want_stale", "want_old"), [
    ("fresh", _ctx("available"), {"a": _q(0), "b": _q(1)}, False, 1),
    ("provider stale", _ctx("stale"), {"a": _q(10), "b": _q(10)}, True, 10),
    ("no price at all", _ctx("available"), {}, True, None),
    ("one leg has no quote", _ctx("available"), {"a": _q(0)}, True, 0),
    ("mixed: one leg stale", _ctx("available"), {"a": _q(0), "b": _q(12, DataHealth.STALE)}, True, 12),
    ("context missing", None, {"a": _q(0), "b": _q(0)}, True, 0),
    ("health unknown", _ctx("unavailable"), {"a": _q(0), "b": _q(0)}, True, 0),
])
def test_leg_prices_state_every_answer_state_unknown_is_stale(name, ctx, quotes, want_stale, want_old):
    at, stale = readers.leg_prices_state(ctx, quotes, IDS, POS)
    assert stale is want_stale, name
    assert at == (None if want_old is None else NOW - datetime.timedelta(minutes=want_old)), name


def test_prices_block_naive_timestamp_is_unknown_age_and_stale():
    m = dataclasses.replace(market_of(load("ADJ-02")), prices_stale=True, prices_at=datetime.datetime(2026, 1, 1))  # noqa: DTZ001 - naive on purpose
    p = route._prices_block(m)
    assert p["stale"] is True and p["age_minutes"] is None and p["as_of"] is None


# issue 91: the 14:30 time-exit clock reads the IST wall clock, whatever zone `now` carries
@pytest.mark.parametrize(("now", "hhmm"), [
    (datetime.datetime(2026, 11, 10, 14, 20, tzinfo=IST), "14:20"),
    (datetime.datetime(2026, 11, 10, 8, 50, tzinfo=datetime.UTC), "14:20"),
    (datetime.datetime(2026, 11, 10, 14, 30, tzinfo=IST), "14:30"),
    (datetime.datetime(2026, 11, 10, 9, 0, tzinfo=datetime.UTC), "14:30"),
])
def test_91_time_exit_clock_is_ist_and_not_due_before_1430(now, hhmm):
    pos = Position("NIFTY", 75, "weekly", datetime.date(2026, 11, 10), (LEG,))
    guards = {"time_exit": "14:30"}
    exits = check.exit_inputs_of(guards, pos, now)
    assert exits.hhmm == hhmm and exits.time_exit == "14:30"
    if hhmm < "14:30":
        with pytest.raises(Exception, match="14:30"):
            ap._time_exit_due(pos, exits)
    else:
        ap._time_exit_due(pos, exits)
