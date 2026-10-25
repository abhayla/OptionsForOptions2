"""Builder warnings as engine codes on measured conditions (REQ-085, ADR-185, ADR-003; standard library only).

``strategy_warnings`` is called ONCE, from ``build_outcome`` (a computed answer), and never from the not-live, waiting,
refused or from-entries paths: those answers carry ``warnings`` absent, not an empty list (an absent list is not "No
warnings for this strategy", AC-8). The one door to the browser stays ``ofo_app.routes.outcome.outcome_response``, so
the REST answer, the live push and the leg-edit embed carry the same codes.

Codes: unhedged_short (strategy level, one per direction, ADR-185), weekend_holiday_decay (strategy level),
low_liquidity and liquidity_unknown (per leg), expiry_day (per leg, W-086's own test and wording), and market_event
(held, AC-6: the code exists in the enum and is never emitted here).

Answer states (run-discipline B4 (d)):
- a leg with no lot size / quantity: the whole list is refused (``None``, logged), never a silent partial list.
- liquidity: depth stated -> spread / no-bid / no-offer tests; depth absent (quote or ltp packet, feed not healthy)
  or the leg's quote not AVAILABLE -> ``liquidity_unknown``, never a verdict from stale data (ADR-015); depth empty on
  both sides -> low_liquidity (no bid or offer); no trade time -> "no trade" (only when the
  depth is live.
- calendar: next open stated -> days; a year missing (CalendarError / None) -> no decay code; theta total absent
  (no Greeks) or zero -> no decay code.
"""
from __future__ import annotations

import datetime
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from ofo.engine.decay import decay_estimate
from ofo.engine.legs import Action, Instrument
from ofo.errors.explanations import ExplanationText, render_explanation
from ofo.execution.safety import expires_today
from ofo.execution.sequence import expiry_covers
from ofo.market_calendar import CalendarError
from ofo.rules.inputs import DataHealth
from ofo.timeutil import IST

if TYPE_CHECKING:
    from ofo.outcome.service import OutcomeLeg
    from ofo.outcome.snapshot import MarketSnapshot

log = logging.getLogger(__name__)

#: AC-4 defaults of the two admin settings (``ofo_app.config.Settings`` takes its defaults from here: one home).
DEFAULT_NO_TRADE_MINUTES = 5
DEFAULT_MAX_SPREAD_PERCENT = Decimal(10)
_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MIN_DECAY_DAYS = 2  # AC-3: the next trading day is two or more calendar days away
_HALF = Decimal(200)  # spread % of mid = (ask - bid) * 200 / (ask + bid)


class WarningCode(Enum):
    UNHEDGED_SHORT = "unhedged_short"
    WEEKEND_HOLIDAY_DECAY = "weekend_holiday_decay"
    LOW_LIQUIDITY = "low_liquidity"
    LIQUIDITY_UNKNOWN = "liquidity_unknown"
    EXPIRY_DAY = "expiry_day"
    MARKET_EVENT = "market_event"  # held (ADR-156 (3)): never emitted by this module


@dataclass(frozen=True)
class LiquiditySettings:
    """The two AC-4 admin settings, read once by the app (``Settings``) and passed in."""

    no_trade_minutes: int = DEFAULT_NO_TRADE_MINUTES
    max_spread_percent: Decimal = DEFAULT_MAX_SPREAD_PERCENT


@dataclass(frozen=True)
class Warning_:
    code: WarningCode
    text: ExplanationText


def _signed(leg: OutcomeLeg) -> int:
    return leg.quantity if leg.action is Action.BUY else -leg.quantity  # type: ignore[operator]


def _uncovered(legs: Sequence[OutcomeLeg], kind: Instrument) -> tuple[int, int]:
    """(sold quantity with no cover, bought quantity left over) for one option type. A bought option covers a sold
    one of the same type whatever its strike, but only if it expires on or after it (``expiry_covers``, the rule
    Execute's ``protects`` uses). Greedy from the latest sold expiry, using the earliest eligible buy first; integers."""
    sold: dict[datetime.date, int] = {}
    bought: dict[datetime.date, int] = {}
    for x in legs:
        if x.instrument is kind:
            side = sold if x.action is Action.SELL else bought
            side[x.expiry] = side.get(x.expiry, 0) + x.quantity  # type: ignore[index, operator]
    uncovered = 0
    for sold_expiry in sorted(sold, reverse=True):
        need = sold[sold_expiry]
        for bought_expiry in sorted(bought):
            if need and expiry_covers(bought_expiry, sold_expiry):
                take = min(need, bought[bought_expiry])
                bought[bought_expiry] -= take
                need -= take
        uncovered += need
    return uncovered, sum(bought.values())


def unhedged_directions(legs: Sequence[OutcomeLeg]) -> tuple[bool, bool]:
    """ADR-185: (rising, falling) - whether the loss has no fixed limit when the index rises / falls. Integer
    quantities only (lots x lot size). A bought option of the same type covers a sold one whatever its strike
    (ADR-143 (2)) but only if it expires on or after it - the same answer as ``execution.sequence.protects`` (a
    reverse calendar is warned). Net futures are unchanged: long futures cover sold calls, short futures cover sold
    puts, and a left-over bought option offsets a short (calls) or long (puts) future."""
    calls, spare_calls = _uncovered(legs, Instrument.CE)
    puts, spare_puts = _uncovered(legs, Instrument.PE)
    futures = sum(_signed(x) for x in legs if x.instrument is Instrument.FUT)
    rising = calls > max(futures, 0) or (futures < 0 and -futures > spare_calls)
    falling = puts > max(-futures, 0) or (futures > 0 and futures > spare_puts)
    return rising, falling


def _unhedged(legs: Sequence[OutcomeLeg], underlying: str) -> list[Warning_]:
    rising, falling = unhedged_directions(legs)
    out = []
    if rising:
        out.append(Warning_(WarningCode.UNHEDGED_SHORT, render_explanation("warn_unhedged_rising",
                                                                          underlying=underlying)))
    if falling:
        out.append(Warning_(WarningCode.UNHEDGED_SHORT, render_explanation("warn_unhedged_falling",
                                                                          underlying=underlying)))
    return out


def _decay(valuation: datetime.datetime, theta_total: Decimal | None,
           calendar: Callable[[datetime.datetime], datetime.datetime | None]) -> list[Warning_]:
    """AC-3: the next trading day two or more calendar days away and a non-zero theta total."""
    if theta_total is None or theta_total == 0:
        return []
    try:
        nxt = calendar(valuation)
    except CalendarError:
        return []
    if nxt is None:  # a year missing from the calendar data: no guess
        return []
    nxt_day = nxt.astimezone(IST).date()
    days = (nxt_day - valuation.astimezone(IST).date()).days
    if days < MIN_DECAY_DAYS:
        return []
    return [Warning_(WarningCode.WEEKEND_HOLIDAY_DECAY, render_explanation(
        "warn_weekend_holiday_decay", days=days, day=_WEEKDAYS[nxt_day.weekday()],
        amount=decay_estimate(theta_total, days)))]


def _liquidity(leg: OutcomeLeg, snapshot: MarketSnapshot, valuation: datetime.datetime,
               settings: LiquiditySettings) -> list[Warning_]:
    unknown = [Warning_(WarningCode.LIQUIDITY_UNKNOWN, render_explanation("warn_liquidity_unknown"))]
    lm = snapshot.legs.get(leg.instrument_id)
    quote = None if lm is None else lm.quote
    held = snapshot.liquidity.get(leg.instrument_id)
    if quote is None or quote.health is not DataHealth.AVAILABLE or held is None or held.depth is None:
        return unknown
    out: list[Warning_] = []
    bid = held.depth.bids[0].price if held.depth.bids else None
    ask = held.depth.asks[0].price if held.depth.asks else None
    if not bid or not ask:
        out.append(Warning_(WarningCode.LOW_LIQUIDITY, render_explanation("warn_low_liquidity_no_quote")))
    elif (ask - bid) * _HALF > settings.max_spread_percent * (ask + bid):
        percent = ((ask - bid) * _HALF / (ask + bid)).quantize(Decimal("0.1"))
        out.append(Warning_(WarningCode.LOW_LIQUIDITY, render_explanation("warn_low_liquidity_spread",
                                                                         percent=percent)))
    minutes = datetime.timedelta(minutes=settings.no_trade_minutes)
    traded = None if not held.last_trade_ts else datetime.datetime.fromtimestamp(held.last_trade_ts, IST)
    if traded is None or valuation - traded > minutes:
        out.append(Warning_(WarningCode.LOW_LIQUIDITY, render_explanation("warn_low_liquidity_no_trade",
                                                                         minutes=settings.no_trade_minutes)))
    return out


def _expiry_day(leg: OutcomeLeg, valuation: datetime.datetime) -> list[Warning_]:
    """W-086's rule and wording, unchanged: the same predicate and the same templates as the Execute flags."""
    if leg.symbol is None or not expires_today(leg.expiry, valuation):
        return []
    if leg.instrument is Instrument.FUT:
        key = "flag_expiry_day_future_short" if leg.action is Action.SELL else "flag_expiry_day_future"
    else:
        key = "flag_expiry_day_short" if leg.action is Action.SELL else "flag_expiry_day_entry"
    return [Warning_(WarningCode.EXPIRY_DAY, render_explanation(key, symbol=leg.symbol))]


def strategy_warnings(definition, legs: Sequence[OutcomeLeg], snapshot: MarketSnapshot,  # noqa: PLR0913
                      valuation: datetime.datetime, *, totals_theta: Decimal | None,
                      calendar: Callable[[datetime.datetime], datetime.datetime | None],
                      liquidity_settings: LiquiditySettings) -> tuple[list[Warning_], dict[str, list[Warning_]]] | None:
    """(strategy-level warnings, warnings per leg by instrument id), or ``None`` when a leg has no quantity (the whole
    list is refused and logged: a partial list would read as "no warning")."""
    if any(x.quantity is None or x.lot_size is None for x in legs):
        log.error("warnings refused: a leg of %s has no lot size", definition.underlying)
        return None
    if any(x.instrument in (Instrument.CE, Instrument.PE) and x.expiry is None for x in legs):
        log.error("warnings refused: an option leg of %s has no expiry", definition.underlying)  # cover needs it
        return None
    strategy = _unhedged(legs, snapshot.underlying) + _decay(valuation, totals_theta, calendar)
    per_leg = {x.instrument_id: _liquidity(x, snapshot, valuation, liquidity_settings) + _expiry_day(x, valuation)
               for x in legs}
    return strategy, per_leg


def no_warnings_label() -> ExplanationText:
    """AC-8: the server sends the empty-state words, so the browser builds no text."""
    return render_explanation("warnings_none")
