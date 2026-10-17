"""W-095: the parts of the Execute route that need no database (REQ-073 AC-1, ADR-080 (3), ADR-050 item 4).

- ``book_floor``: today's Zerodha order book -> the highest plan number this strategy's tags carry, and whether any
  such order is still open. Terminal = COMPLETE, CANCELLED, REJECTED (an allow-list); any other or unknown status word
  is NOT terminal (fail closed, finding trust-broker-status-word). A tag is this strategy's only when ``parse_tag``
  decodes it exactly to this id (``OFS12V3L0`` is strategy 12, never 1).
- ``price_legs``: one function for ENTRY (legs from the stored definition) and EXIT (the held legs, opposite side):
  each leg's LIMIT is ``executable_limit`` on the leg's REAL depth quote (ADR-080 (3): "the worst price level in
  Kite's 5-level depth needed to fill the whole quantity (BUY: ask side, SELL: bid side)"), checked against the
  quote's circuit band (``circuit_block``). No quote, a depth that cannot fill, or a price outside the band refuses the
  leg with the catalogue message; a price is never taken from the stored plan alone. ``planned_price`` (the slippage
  base only) is the leg's stored planned entry, else the quote's last price.
- ``broker_mismatch``: Zerodha's net units per contract (positions reply through the W-091 adapter) against the units
  this strategy holds by its stored filled plans; any difference on one of this strategy's contracts blocks it.
"""
from __future__ import annotations

import datetime
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.engine.executable_price import depth_from_quote, executable_limit
from ofo.errors import LegValue, UserFacingError, render
from ofo.execution.basket import parse_tag
from ofo.execution.planned import ExecutionPlan, PlannedLeg
from ofo.execution.price_check import circuit_block
from ofo.instruments.catalogue import Catalogue
from ofo.instruments.models import ZERODHA, InstrumentId
from ofo.timeutil import IST

#: Zerodha's order statuses after which an order can no longer fill (an allow-list; anything else is open).
TERMINAL_ORDER_STATUSES = frozenset({"COMPLETE", "CANCELLED", "REJECTED"})
_QUOTE_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

QuoteOf = Callable[[str], Mapping[str, object] | None]


class LegRefused(ValueError):
    """One leg cannot be priced; ``message`` is the catalogue text the route shows (409)."""

    def __init__(self, message: UserFacingError) -> None:
        super().__init__(message.what_happened)
        self.message = message


def book_floor(rows: Sequence[object], strategy_id: int) -> tuple[int, bool]:
    """(highest plan number among THIS strategy's tags, True when any of those orders is not terminal)."""
    floor, still_open = 0, False
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("an order row must be a mapping")  # an unreadable book never passes
        try:
            parts = parse_tag(row.get("tag"))
        except ValueError:
            continue  # not a basket tag of ours
        if parts.strategy_id != strategy_id:
            continue
        floor = max(floor, parts.plan_version)
        if row.get("status") not in TERMINAL_ORDER_STATUSES:
            still_open = True
    return floor, still_open


@dataclass(frozen=True)
class LegToPrice:
    instrument_id: InstrumentId
    action: Action
    quantity: int
    planned_entry: Decimal | None  # the stored planned entry (ADR-075), None -> the quote's last price


@dataclass(frozen=True)
class PricedPlan:
    strategy: Strategy
    plan: ExecutionPlan
    price_bands: Mapping[tuple, tuple[Decimal, Decimal]]
    quote_times: tuple[datetime.datetime, ...]


def _money(value: object) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (Decimal, int)):
        return None  # a float or text money figure is never read (money-parsed-through-float)
    return Decimal(value)


def quote_time(quote: Mapping[str, object]) -> datetime.datetime | None:
    """The quote's own timestamp (Kite's IST wall time), aware; None when absent or unreadable."""
    raw = quote.get("timestamp")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.datetime.strptime(raw, _QUOTE_TIME_FORMAT).replace(tzinfo=IST)
    except ValueError:
        return None


def price_legs(strategy_id: str, underlying: str, legs: Sequence[LegToPrice], catalogue: Catalogue,
               quote_of: QuoteOf) -> PricedPlan:
    """Price every leg from its own depth quote (module docstring); raises ``LegRefused`` for the first leg that
    cannot be priced, ``ValueError`` for a contract the catalogue cannot resolve."""
    planned, engine_legs, bands, times = [], [], {}, []
    for number, want in enumerate(legs, start=1):
        entry = catalogue.get(want.instrument_id)
        ref = entry.ref(ZERODHA)
        c = entry.contract
        leg_at = Leg(want.action, Instrument(c.instrument_type), c.strike, c.expiry, want.quantity, Decimal("0.05"))
        shown = LegValue(number, leg_at, underlying)
        quote = quote_of(ref.broker_token)
        lower = upper = None
        if isinstance(quote, Mapping):
            lower, upper = _money(quote.get("lower_circuit_limit")), _money(quote.get("upper_circuit_limit"))
        base = want.planned_entry if want.planned_entry is not None else (
            _money(quote.get("last_price")) if isinstance(quote, Mapping) else None)
        when = quote_time(quote) if isinstance(quote, Mapping) else None
        if quote is None or lower is None or upper is None or base is None or base <= 0 or when is None:
            raise LegRefused(render("gate_price_not_known", leg=shown))
        try:
            result = executable_limit(depth_from_quote(quote), want.action, want.quantity, ref.tick_size, base)
        except ValueError:
            raise LegRefused(render("gate_price_not_known", leg=shown)) from None
        if not result.fillable or result.limit is None:
            raise LegRefused(render("gate_price_not_known", leg=shown))
        blocked = circuit_block(result.limit, lower, upper, shown)
        if blocked is not None:
            raise LegRefused(blocked)
        leg = Leg(want.action, Instrument(c.instrument_type), c.strike, c.expiry, want.quantity, result.limit)
        engine_legs.append(leg)
        planned.append(PlannedLeg(f"L{number}", ref.broker_symbol, leg))
        bands[(leg.expiry, leg.instrument.value, leg.strike)] = (lower, upper)
        times.append(when)
    return PricedPlan(Strategy(tuple(engine_legs), underlying), ExecutionPlan(strategy_id, tuple(planned)), bands,
                      tuple(times))


ContractKey = tuple  # (underlying, Instrument, strike | None, expiry): the W-091 reconcile key


def contract_key(catalogue: Catalogue, instrument_id: InstrumentId, underlying: str) -> ContractKey:
    c = catalogue.get(instrument_id).contract
    kind = Instrument(c.instrument_type)
    return (underlying, kind, None if kind is Instrument.FUT else c.strike, c.expiry)


def broker_mismatch(broker_net: Mapping[ContractKey, int], held: Mapping[ContractKey, int],
                    contracts: Sequence[ContractKey]) -> bool:
    """True when Zerodha's net units differ from what the strategy holds on any of ``contracts`` (fail closed: units
    the strategy does not explain on its own contract count as a mismatch)."""
    return any(broker_net.get(k, 0) != held.get(k, 0) for k in set(contracts) | set(held))


__all__ = ["TERMINAL_ORDER_STATUSES", "LegRefused", "LegToPrice", "PricedPlan", "book_floor", "broker_mismatch",
           "contract_key", "price_legs", "quote_time"]
