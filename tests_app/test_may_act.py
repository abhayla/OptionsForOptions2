"""B4 (Phase 2 of the modular plan, 25 Nov 2026): ONE server answer to "may this act now?" (market open, prices live).

Spec basis: ADR-212 (no paper fill outside market hours; ``gate_market_closed``), ADR-119 (the market calendar, through
the feed's own state), ADR-327 (a trigger save in market hours needs a live price; closed: saved), REQ-109 AC-5 (an exit
needs a live price for every named leg: ``tracking_exit_prices_not_live``), ADR-015 (a stale price is never live).

Core: one action x one state table. The four states a caller meets are open+live, open+stale, open+missing and closed;
every refusal keeps the code and failure the route raised before the door existed. No database, no real clock: the
market time is the ``at`` argument, the provider is the recorded replay's.
"""
from __future__ import annotations

import datetime
import pathlib
import sys
from decimal import Decimal

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from marketdata._kite_fixture import new_provider  # noqa: E402
from ofo.timeutil import IST  # noqa: E402
from ofo_app import may_act as door  # noqa: E402
from ofo_app.errors import Failure  # noqa: E402
from ofo_app.routes.outcome import MarketContext, market_state  # noqa: E402
from ofo_app.strategy_refused import StrategyRefused  # noqa: E402

OPEN_AT = datetime.datetime(2026, 10, 8, 10, 0, tzinfo=IST)  # a Thursday session
CLOSED_AT = datetime.datetime(2026, 10, 8, 20, 0, tzinfo=IST)
CLOSED, UNREADABLE, EXIT_NOT_LIVE = "gate_market_closed", "paper_trigger_price_unreadable", "tracking_exit_prices_not_live"


@pytest.fixture
def ctx():
    provider, clock, _items = new_provider()
    return MarketContext(provider, clock, Decimal("0.065"))


def test_open_and_live_every_action_is_allowed(ctx):
    for action in ("place", "exit", "set_trigger"):
        assert door.may_act(ctx, action, OPEN_AT, ["live", "live"]) == door.Allowed(market_open=True)


@pytest.mark.parametrize("state", ["stale", "missing"])
def test_open_and_a_price_not_live_refuses_an_exit_and_a_trigger_by_name(ctx, state):
    assert door.may_act(ctx, "exit", OPEN_AT, ["live", state]) == door.Refused(EXIT_NOT_LIVE, Failure.CONFLICT)
    assert door.may_act(ctx, "set_trigger", OPEN_AT, [state]) == door.Refused(UNREADABLE, None)


@pytest.mark.parametrize("state", ["stale", "missing"])
def test_a_place_reads_no_price_so_prices_never_refuse_it(ctx, state):
    assert door.may_act(ctx, "place", OPEN_AT, [state]) == door.Allowed(market_open=True)


def test_closed_refuses_a_place_and_an_exit_even_with_live_prices(ctx):
    for action in ("place", "exit"):
        assert door.may_act(ctx, action, CLOSED_AT, ["live"]) == door.Refused(CLOSED, Failure.CONFLICT)
        assert door.may_act(ctx, action, CLOSED_AT) == door.Refused(CLOSED, Failure.CONFLICT)


def test_closed_a_trigger_is_allowed_and_says_the_market_is_shut(ctx):
    """ADR-327 (3): market closed, the level is saved and arms at the next live tick; prices are not judged."""
    assert door.may_act(ctx, "set_trigger", CLOSED_AT, ["missing"]) == door.Allowed(market_open=False)


def test_prices_not_given_judge_the_market_only(ctx):
    assert door.may_act(ctx, "exit", OPEN_AT) == door.Allowed(market_open=True)
    assert door.may_act(ctx, "exit", OPEN_AT, []) == door.Allowed(market_open=True)  # nothing to price


def test_no_market_context_fails_closed_by_the_calendar():
    assert door.may_act(None, "place", CLOSED_AT) == door.Refused(CLOSED, Failure.CONFLICT)
    assert door.may_act(None, "place", OPEN_AT) == door.Allowed(market_open=True)


def test_an_unknown_action_is_a_programming_error(ctx):
    with pytest.raises(ValueError):
        door.may_act(ctx, "buy_now", OPEN_AT)  # type: ignore[arg-type]


def test_an_unknown_price_state_is_not_live(ctx):
    assert door.may_act(ctx, "exit", OPEN_AT, ["live", "weird"]) == door.Refused(EXIT_NOT_LIVE, Failure.CONFLICT)


@pytest.mark.parametrize("hh,mm", [(9, 14), (9, 15), (15, 29), (15, 30), (15, 44), (15, 45)])
def test_the_market_half_is_exactly_market_state_at_the_session_edges(ctx, hh, mm):
    """The answer the old gate gave (``paper_limit.refuse_when_closed``) was ``market_state(ctx, at).closed``: the door
    agrees at every edge of the session, including the 15:30 to 15:45 settlement window."""
    at = datetime.datetime(2026, 10, 8, hh, mm, tzinfo=IST)
    assert door.market_open(ctx, at) is (not market_state(ctx, at).closed)
    assert (door.may_act(ctx, "place", at) == door.Refused(CLOSED, Failure.CONFLICT)) is market_state(ctx, at).closed


def test_require_raises_the_refusal_route_code_and_passes_an_allowed(ctx):
    door.require(door.may_act(ctx, "place", OPEN_AT))
    with pytest.raises(StrategyRefused) as gone:
        door.require(door.may_act(ctx, "place", CLOSED_AT))
    assert gone.value.args == (CLOSED,)
    assert gone.value.failure is Failure.CONFLICT
    with pytest.raises(StrategyRefused) as unread:
        door.require(door.may_act(ctx, "set_trigger", OPEN_AT, ["stale"]))
    assert unread.value.args == (UNREADABLE,)
    assert unread.value.failure is None


def test_prices_ok_is_the_price_half_alone():
    assert door.prices_ok("exit", ["live"]) == door.Allowed(market_open=True)
    assert door.prices_ok("exit", ["live", "stale"]) == door.Refused(EXIT_NOT_LIVE, Failure.CONFLICT)
    assert door.prices_ok("set_trigger", ["missing"]) == door.Refused(UNREADABLE, None)
    assert door.prices_ok("place", ["missing"]) == door.Allowed(market_open=True)
