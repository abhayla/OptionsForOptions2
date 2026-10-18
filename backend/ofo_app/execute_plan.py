"""W-095: the parts of the Execute route that need no database (REQ-073 AC-1, ADR-080 (3), ADR-050 item 4).

- ``book_floor``: today's Zerodha order book -> the highest plan number this strategy's tags carry, and whether any
  such order is still open. Terminal = COMPLETE, CANCELLED, REJECTED (an allow-list); any other or unknown status word
  is NOT terminal (fail closed, finding trust-broker-status-word). A tag is this strategy's only when ``parse_tag``
  decodes it exactly to this id (``OFS12V3L0`` is strategy 12, never 1).
- ``price_legs``: one function for ENTRY (legs from the stored definition) and EXIT (the held legs, opposite side):
  each leg's LIMIT is ``executable_limit`` on the leg's REAL depth (ADR-080 (3): "the worst price level in Kite's
  5-level depth needed to fill the whole quantity (BUY: ask side, SELL: bid side)"), checked against the circuit band
  when the source carries one (``circuit_block``). No depth, a depth that cannot fill, or a price outside the band
  refuses the leg with the catalogue message; a price is never taken from the stored plan alone. ``planned_price``
  (the slippage base only) is the leg's stored planned entry, else the quote's last price, else the leg is refused.
- ``strategy_blocked`` (REQ-060 AC-7): Zerodha's net units per contract against the units this strategy holds by its
  stored filled plans; FEWER units at Zerodha, or the opposite side, block it; units beyond it block nothing.
  ``ofo.reconciliation.compare`` is not used: it attributes ANY difference on a held contract to the holder (a
  surplus included) and has no input for "a position in no strategy and not recorded as standalone", so it would
  block on a surplus that AC-7 says "blocks no strategy".
"""
from __future__ import annotations

import datetime
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.engine.executable_price import Depth, depth_from_quote, executable_limit
from ofo.errors import LegValue, UserFacingError, render
from ofo.execution.basket import parse_tag
from ofo.execution.context import VersionState
from ofo.execution.planned import ExecutionPlan, PlannedLeg
from ofo.execution.price_check import circuit_block
from ofo.instruments.catalogue import Catalogue
from ofo.instruments.models import ZERODHA, InstrumentId
from ofo.timeutil import IST

#: Zerodha's order statuses after which an order can no longer fill (an allow-list; anything else is open).
TERMINAL_ORDER_STATUSES = frozenset({"COMPLETE", "CANCELLED", "REJECTED"})
_QUOTE_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class LegQuote:
    """What one leg is priced from: Kite's 5-level depth, when it was read, and (when the source carries them) the
    last price and the day's circuit band. A source without a band leaves ``band`` None: the gate then blocks an
    entry leg (``gate_price_band_unknown``) and asks to confirm an exit, which the route refuses (fail closed)."""

    depth: Depth
    at: datetime.datetime
    last_price: Decimal | None = None
    band: tuple[Decimal, Decimal] | None = None


QuoteOf = Callable[[InstrumentId, str], LegQuote | None]  # (instrument id, broker token) -> quote or None


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


def quote_from_kite(quote: object) -> LegQuote | None:
    """A Kite full quote (REST ``/quote`` shape, money as Decimal) -> ``LegQuote``; None when the depth or the time
    cannot be read. A missing band stays None (the gate decides), never a made-up band."""
    if not isinstance(quote, Mapping):
        return None
    when = quote_time(quote)
    try:
        depth = depth_from_quote(quote)
    except ValueError:
        return None
    if when is None:
        return None
    lower, upper = _money(quote.get("lower_circuit_limit")), _money(quote.get("upper_circuit_limit"))
    band = None if lower is None or upper is None else (lower, upper)
    return LegQuote(depth, when, _money(quote.get("last_price")), band)


def _price_one(number: int, want: LegToPrice, underlying: str, catalogue: Catalogue,
               quote_of: QuoteOf) -> tuple[PlannedLeg, LegQuote]:
    entry = catalogue.get(want.instrument_id)
    ref = entry.ref(ZERODHA)
    c = entry.contract
    shown = LegValue(number, Leg(want.action, Instrument(c.instrument_type), c.strike, c.expiry, want.quantity,
                                 ref.tick_size), underlying)
    quote = quote_of(want.instrument_id, ref.broker_token)
    if not isinstance(quote, LegQuote):
        raise LegRefused(render("gate_price_not_known", leg=shown))
    base = want.planned_entry if want.planned_entry is not None else quote.last_price
    if base is None or base <= 0:
        raise LegRefused(render("gate_price_not_known", leg=shown))
    try:
        result = executable_limit(quote.depth, want.action, want.quantity, ref.tick_size, base)
    except ValueError:
        raise LegRefused(render("gate_price_not_known", leg=shown)) from None
    if not result.fillable or result.limit is None:
        raise LegRefused(render("gate_price_not_known", leg=shown))
    if quote.band is not None:
        blocked = circuit_block(result.limit, quote.band[0], quote.band[1], shown)
        if blocked is not None:
            raise LegRefused(blocked)
    leg = Leg(want.action, Instrument(c.instrument_type), c.strike, c.expiry, want.quantity, result.limit)
    return PlannedLeg(f"L{number}", ref.broker_symbol, leg), quote


def price_legs(strategy_id: str, underlying: str, legs: Sequence[LegToPrice], catalogue: Catalogue,
               quote_of: QuoteOf) -> PricedPlan:
    """Price every leg from its own depth (module docstring); raises ``LegRefused`` for the first leg that cannot be
    priced, ``ValueError`` for a contract the catalogue cannot resolve."""
    planned, bands, times = [], {}, []
    for number, want in enumerate(legs, start=1):
        leg_plan, quote = _price_one(number, want, underlying, catalogue, quote_of)
        planned.append(leg_plan)
        leg = leg_plan.leg
        if quote.band is not None:
            bands[(leg.expiry, leg.instrument.value, leg.strike)] = quote.band
        times.append(quote.at)
    return PricedPlan(Strategy(tuple(p.leg for p in planned)), ExecutionPlan(strategy_id, tuple(planned)), bands,
                      tuple(times))


class _StoredOrder(Protocol):
    instrument_id: str
    transaction_type: str
    filled_quantity: int | None


class _StoredPlan(Protocol):
    plan_number: int
    orders: Sequence[_StoredOrder]


def held_units(history: Iterable[_StoredPlan]) -> dict[str, int]:
    """ADR-105: what the strategy holds = the net of Zerodha's filled quantities over ALL its stored plans, per
    contract (the plan order's ``instrument_id``), BUY + / SELL -; an order not yet closed (None) counts 0. Contracts
    that net to zero are dropped. The ONE source the route reads for exit legs, the active legs and their hash, the
    version state and the reconciliation platform side (round 2 review CRITICAL: one plan was read, never the net)."""
    units: dict[str, int] = {}
    for stored in history:
        for order in stored.orders:
            filled = order.filled_quantity or 0
            signed = filled if order.transaction_type == Action.BUY.value else -filled
            units[order.instrument_id] = units.get(order.instrument_id, 0) + signed
    return {contract: net for contract, net in units.items() if net != 0}


def instrument_id_of(text_id: str) -> InstrumentId:
    """A stored plan order's ``instrument_id`` text (``segment:token``, the live feed's key) as the catalogue's id."""
    segment, token = text_id.split(":")
    return InstrumentId(segment, int(token))


def held_by_instrument(history: Iterable[_StoredPlan]) -> dict[InstrumentId, int]:
    """``held_units`` keyed by catalogue id, the shape ``reduces_held_only`` reads (#338): one derivation, two keys."""
    return {instrument_id_of(contract): net for contract, net in held_units(history).items()}


def latest_filled_plan(history: Iterable[_StoredPlan]) -> int | None:
    """The number of the latest plan any of whose orders filled (the held position's version), or None."""
    numbers = [p.plan_number for p in history if any(o.filled_quantity for o in p.orders)]
    return max(numbers) if numbers else None


def version_state(action: str, held: Mapping[str, int]) -> VersionState:
    """Derived, never hard-coded: a flat strategy (no fills ever, or every fill closed) executes its stored definition
    as an ENTRY; a held net is the ACTIVE version an EXIT closes. A new ENTRY while units are held would add to the
    position (an adjustment, PROPOSED only), and an EXIT with nothing held would open one: both are not executable."""
    holding = any(held.values())
    if action == "EXIT":
        return VersionState.ACTIVE if holding else VersionState.SUPERSEDED
    return VersionState.SUPERSEDED if holding else VersionState.ACTIVE


def exit_legs(held: Mapping[str, int], instrument_of: Callable[[str], InstrumentId]) -> list[LegToPrice]:
    """ADR-105: an exit closes exactly the net, opposite side, per contract (sorted for a stable basket order)."""
    return [LegToPrice(instrument_of(contract), Action.SELL if net > 0 else Action.BUY, abs(net), None)
            for contract, net in sorted(held.items()) if net != 0]


ContractKey = tuple  # (underlying, Instrument, strike | None, expiry): the W-091 reconcile key


def contract_key(catalogue: Catalogue, instrument_id: InstrumentId, underlying: str) -> ContractKey:
    c = catalogue.get(instrument_id).contract
    kind = Instrument(c.instrument_type)
    return (underlying, kind, None if kind is Instrument.FUT else c.strike, c.expiry)


def strategy_blocked(broker_net: Mapping[ContractKey, int], held: Mapping[ContractKey, int]) -> bool:
    """REQ-060 AC-7 for ONE strategy: blocked when, on a contract it holds, Zerodha holds FEWER units than the
    strategy, or the opposite side. Units BEYOND the strategy's (a position in no strategy) block nothing: they are
    offered the grouping choice (Q24). Signed units: BUY +, SELL -."""
    for key, units in held.items():
        if units == 0:
            continue
        net = broker_net.get(key, 0)
        if (net > 0) != (units > 0) or abs(net) < abs(units):
            return True
    return False


__all__ = ["TERMINAL_ORDER_STATUSES", "LegQuote", "LegRefused", "LegToPrice", "PricedPlan", "book_floor",
           "contract_key", "exit_legs", "held_units", "latest_filled_plan", "price_legs", "quote_from_kite",
           "quote_time", "strategy_blocked", "version_state"]
