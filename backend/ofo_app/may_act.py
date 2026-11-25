"""The ONE server answer to "may this act now?" (B4 of the modular plan, 25 Nov 2026): the market is open, the prices an
action needs are live.

Spec basis: ADR-212 (no paper fill outside market hours: ``gate_market_closed``); ADR-119 (the market calendar, read
through the feed's own state, ``routes.outcome.market_state``); ADR-327 (a trigger save in market hours needs a live
price, market closed saves); REQ-109 AC-5 (an exit needs a live price for every named leg); ADR-015 (a stale price is
never live).

Before this door the same question was asked in separate places: ``paper_limit.refuse_when_closed`` (two routes and the
shared save), ``check_trigger_levels`` and ``market_read.read_market`` (each ``market_state(...).closed``), the exit
price check in ``_server_exit_prices``, and the trigger judge's "price not live". They now call this module, so a rule
changed here changes every caller. Server-only: no endpoint exposes it (the screens use the book-read state,
``priceState``).

Answers, per action (``Allowed.market_open`` says which side of the bell the answer was given on):

- ``place``: market closed -> Refused ``gate_market_closed``; open -> Allowed (a place reads no price here).
- ``exit``: market closed -> Refused ``gate_market_closed``; open and a price not live (stale, missing, unknown) ->
  Refused ``tracking_exit_prices_not_live``.
- ``set_trigger``: market closed -> Allowed with ``market_open`` False (saved, arms at the next live tick); open and a
  price not live -> Refused ``paper_trigger_price_unreadable``.

``prices`` is the state of each price the action needs, as read by its caller (``paper.Price.state`` /
``market_read.MarketPrice.state``). ``None``: not read yet, the market half alone; an empty list: nothing to price.
"""
from __future__ import annotations

import datetime
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Final, Literal

from ofo.tracking import paper

from ofo_app.errors import Failure
from ofo_app.routes.outcome import MarketContext, market_state
from ofo_app.strategy_refused import StrategyRefused

Action = Literal["place", "exit", "set_trigger"]
MISSING: Final = "missing"
GATE_MARKET_CLOSED: Final = "gate_market_closed"  # ADR-212
EXIT_PRICES_NOT_LIVE: Final = "tracking_exit_prices_not_live"  # REQ-109 AC-5
TRIGGER_PRICE_UNREADABLE: Final = "paper_trigger_price_unreadable"  # ADR-327 (2)
#: action -> (what a price that is not live refuses with, whether a closed market refuses)
_RULES: Final[dict[str, tuple[tuple[str, Failure | None] | None, bool]]] = {
    "place": (None, True),
    "exit": ((EXIT_PRICES_NOT_LIVE, Failure.CONFLICT), True),
    "set_trigger": ((TRIGGER_PRICE_UNREADABLE, None), False),
}


@dataclass(frozen=True)
class Allowed:
    market_open: bool = True


@dataclass(frozen=True)
class Refused:
    reason: str  # the catalogue template id the route raised before this door existed
    failure: Failure | None = Failure.CONFLICT


def state_of(price: paper.Price) -> str:
    """A price's state as this door judges it: a price that carries no number is ``missing`` whatever its state says."""
    return price.state if price.price is not None else MISSING


def market_open(ctx: MarketContext | None, at: datetime.datetime) -> bool:
    """The market half alone: the ONE market-state answer (``market_state``) at ``at``; no context fails closed."""
    return not market_state(ctx, at).closed


def _rule(action: str) -> tuple[tuple[str, Failure | None] | None, bool]:
    try:
        return _RULES[action]
    except KeyError:
        raise ValueError(f"unknown action {action!r}") from None


def prices_ok(action: Action, prices: Iterable[str]) -> Allowed | Refused:
    """The price half alone: every state must be ``live`` (anything else, an unknown state included, is not live)."""
    not_live, _closed_refuses = _rule(action)
    if not_live is not None and any(state != paper.LIVE for state in prices):
        return Refused(*not_live)
    return Allowed()


def may_act(ctx: MarketContext | None, action: Action, at: datetime.datetime,
            prices: Iterable[str] | None = None) -> Allowed | Refused:
    """May ``action`` happen at ``at``? Market half first (closed: refused, or for ``set_trigger`` allowed and saved
    unjudged, ADR-327 (3)); then, when ``prices`` were read, the price half."""
    _not_live, closed_refuses = _rule(action)
    if not market_open(ctx, at):
        return Refused(GATE_MARKET_CLOSED, Failure.CONFLICT) if closed_refuses else Allowed(market_open=False)
    return Allowed() if prices is None else prices_ok(action, prices)


def require(decision: Allowed | Refused) -> None:
    """Raise the route's own refusal (``StrategyRefused``, the code and failure it always carried) for a Refused."""
    if isinstance(decision, Refused):
        raise StrategyRefused(decision.reason, decision.failure)


def refuse_unless_allowed(ctx: Any, action: Action, at: datetime.datetime,
                          prices: Iterable[str] | None = None) -> None:
    """``require(may_act(...))``: what a route calls before it writes."""
    require(may_act(ctx, action, at, prices))
