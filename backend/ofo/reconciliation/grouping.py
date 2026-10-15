"""Existing Zerodha positions on connect: suggested groups, user moves, adoption, every choice audited.

Spec: REQ-061 AC-1 (identify possible multi-leg structures), AC-2 (add to an existing strategy, create a new
strategy, or leave it standalone), AC-4 (every grouping decision recorded); ADR-084 ("A group is named only as a
resemblance to a template"; "An adopted leg's entry price is Zerodha's average price for that position"); ADR-006 /
ADR-018 (resemblance only, the user confirms); ADR-002 (every order belongs to a strategy: a standalone position is
shown and never gets an order or a monitor).

Domain layer, standard library plus this repo's own parser, matcher, catalogue and audit log. Nothing here places an
order, reads the broker or monitors anything; AC-3 (monitoring the adopted strategy) and the screen are other items.

* A position is one Zerodha row, keyed by ``PositionKey`` = (contract identity, product): Zerodha sends one row per
  contract AND product, so NRML and MIS rows of one contract are two positions, end to end.
* ``suggest_groups`` drops zero-quantity rows BEFORE parsing, resolves each contract through the catalogue (Zerodha's
  instrument token, else symbol and exchange), and compares the contract's net broker quantity with the strategies
  that hold it: equal = the strategy's, hidden; different quantity or side = shown as ``differs_from_strategy``,
  never hidden. (A strategy definition carries no product, so product is not compared.) The rest are grouped by
  (underlying, expiry); a group carries the matcher's template name as ``resembles`` or None, never a strategy.
  Rows that cannot be adopted are listed in ``unresolved`` with a reason (shown only; never moved or adopted).
* The entry of an adopted leg is Zerodha's EXACT average (a cost, not an order price: never rounded to a tick). A
  leg holds paise, so an average finer than that needs ``set_entry`` first; ``confirm`` then refuses the WHOLE group
  until every row is adoptable (no partial adoption).
* Adding a position to an EXISTING strategy is refused ("not available yet"): the only path found,
  ``propose_modification`` / ``StrategyRecord.edit`` + ``propose_execution``, prepares orders for the added legs and
  would double a leg Zerodha already holds; no order-free way to add held legs to a version exists yet.
* Every action appends exactly ONE entry through the audit log's public ``append`` (``start`` = the suggestion,
  ``move`` / standalone, ``set_entry``, ``confirm``); a refused action changes nothing and appends nothing.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Callable, Iterable, Mapping, Sequence

from ofo.audit.catalogue import EventType
from ofo.audit.log import AuditLog
from ofo.engine.legs import Action, Instrument, Leg, require_price
from ofo.engine.product import Product
from ofo.errors import render
from ofo.execution.partial import position_line_from_kite_row
from ofo.instruments.catalogue import SUPPORTED_UNDERLYINGS, Catalogue
from ofo.instruments.models import ZERODHA, InstrumentId
from ofo.reconciliation.compare import ReconciliationError
from ofo.strategy.definition import StrategyDefinition
from ofo.strategy.matching import MatchResult, match
from ofo.strategy.model import Template, TemplateError

__all__ = [
    "STANDALONE", "AdoptedLeg", "AdoptedStrategy", "EntrySource", "Group", "GroupSuggestion", "GroupingError",
    "GroupingSession", "PositionKey", "Standalone", "SuggestedPosition", "ToGroup", "ToStrategy", "Unresolved",
    "suggest_groups",
]

#: A refused grouping choice: ``message`` is the four-part text from ``render()``; ``str()`` is developer detail.
GroupingError = ReconciliationError

_PAISE = Decimal("0.01")


class EntrySource(Enum):
    FROM_ZERODHA = "from_zerodha"
    EDITED = "edited"


@dataclass(frozen=True)
class PositionKey:
    """One Zerodha position row: the contract's exchange identity AND the product."""

    instrument_id: InstrumentId
    product: Product


@dataclass(frozen=True)
class ToGroup:
    group_id: str


@dataclass(frozen=True)
class ToStrategy:
    """Refused for now (see the module docstring); kept so a caller can ask and get the honest answer."""

    strategy_id: str


@dataclass(frozen=True)
class Standalone:
    pass


STANDALONE = Standalone()
Target = ToGroup | ToStrategy | Standalone


@dataclass(frozen=True)
class SuggestedPosition:
    instrument_id: InstrumentId
    tradingsymbol: str
    underlying: str
    instrument: Instrument
    strike: Decimal | None
    expiry: datetime.date
    net_quantity: int
    average_price: Decimal  # Zerodha's exact average, any number of decimals
    product: Product
    lot_size: int
    tick_size: Decimal

    @property
    def key(self) -> PositionKey:
        return PositionKey(self.instrument_id, self.product)

    @property
    def action(self) -> Action:
        return Action.BUY if self.net_quantity > 0 else Action.SELL

    @property
    def needs_entry(self) -> bool:
        """True when Zerodha's average is finer than paise: the user sets the entry before the leg can be adopted."""
        return self.average_price.quantize(_PAISE) != self.average_price

    def leg(self, entry_price: Decimal | None = None) -> Leg:
        return Leg(self.action, self.instrument, self.strike, self.expiry, abs(self.net_quantity),
                   self.average_price if entry_price is None else entry_price)


@dataclass(frozen=True)
class Group:
    """A suggested group. ``resembles`` is a template NAME the legs look like, or None; never a strategy."""

    id: str
    underlying: str
    expiry: datetime.date
    positions: tuple[SuggestedPosition, ...]
    resembles: str | None


@dataclass(frozen=True)
class Unresolved:
    """A row that is shown but cannot be adopted. ``reason``: not_in_catalogue | not_lot_multiple | unreadable_row |
    unknown_product | differs_from_strategy (``detail`` then holds both net quantities)."""

    tradingsymbol: str
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class GroupSuggestion:
    groups: tuple[Group, ...]
    unresolved: tuple[Unresolved, ...]
    labeller: Callable[[Sequence[SuggestedPosition]], str | None]


@dataclass(frozen=True)
class AdoptedLeg:
    tradingsymbol: str
    instrument_id: InstrumentId
    leg: Leg
    product: Product
    entry_source: EntrySource


@dataclass(frozen=True)
class AdoptedStrategy:
    """A NEW strategy created by the user's confirm. ``resembles`` is information only."""

    strategy_id: str
    underlying: str
    legs: tuple[AdoptedLeg, ...]
    resembles: str | None


def _group_id(underlying: str, expiry: datetime.date) -> str:
    return f"{underlying}:{expiry.isoformat()}"


_UNRESOLVED_TEMPLATE = {
    "not_lot_multiple": "grouping_not_lot_multiple",
    "unknown_product": "grouping_unknown_product",
    "differs_from_strategy": "grouping_differs_from_strategy",
}


def _unresolved_message(item: Unresolved):
    return render(_UNRESOLVED_TEMPLATE.get(item.reason, "grouping_unknown_contract"), contracts=1)


def _contract_key(name: str, instrument: Instrument, strike: Decimal | None, expiry: datetime.date) -> tuple:
    return (name, instrument, strike, expiry)


def _held_by_strategies(strategies: Mapping[str, StrategyDefinition]) -> dict[tuple, int]:
    held: dict[tuple, int] = {}
    for d in strategies.values():
        for leg in d.legs:
            key = _contract_key(d.underlying, leg.instrument, leg.strike, leg.expiry)
            held[key] = held.get(key, 0) + leg.signed_quantity()
    return held


def _make_labeller(catalogue: Catalogue, templates: Iterable[Template] | None, spots: Mapping[str, Decimal] | None):
    template_list = tuple(templates or ())

    def label(positions: Sequence[SuggestedPosition]) -> str | None:
        if not positions or not template_list or not spots:
            return None
        name = positions[0].underlying
        spot = spots.get(name)
        if spot is None:
            return None
        try:
            gap = catalogue.strike_gap(name, min(p.expiry for p in positions))
            legs = [p.leg(_PAISE) for p in positions]  # the shape needs strikes and sides, not the entry price
            result = match(legs, spot=spot, strike_gap=gap, templates=template_list)
        except (ValueError, TemplateError):  # no strike gap, an off-grid strike, an ambiguous catalogue: no label
            return None
        return result.label if isinstance(result, MatchResult) else None

    return label


def _exact_average(value: object) -> Decimal | None:
    """Zerodha's average as an exact Decimal, or None when it is not a finite positive Decimal/int (floats refused)."""
    if isinstance(value, int) and not isinstance(value, bool):
        value = Decimal(value)
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        return None
    return value


def suggest_groups(
    rows: Sequence[Mapping[str, object]],
    strategies: Mapping[str, StrategyDefinition],
    catalogue: Catalogue,
    *,
    templates: Iterable[Template] | None = None,
    spots: Mapping[str, Decimal] | None = None,
) -> GroupSuggestion:
    """Group the open Kite position rows that no strategy holds, by (underlying, expiry). See the module docstring."""
    by_token: dict[str, list] = {}
    for entry in catalogue.all_entries():
        ref = entry.broker_refs.get(ZERODHA)
        if ref is not None:
            by_token.setdefault(ref.broker_token, []).append(entry)
    held = _held_by_strategies(strategies)

    unresolved: list[Unresolved] = []
    candidates: list[tuple[tuple, SuggestedPosition]] = []
    seen: set[PositionKey] = set()
    for raw in rows:
        symbol = str(raw.get("tradingsymbol", "?")) if isinstance(raw, Mapping) else "?"
        quantity = raw.get("quantity") if isinstance(raw, Mapping) else None
        if quantity == 0 and not isinstance(quantity, bool):
            continue  # a closed row is not an open position; dropped before parsing (its average is 0)
        average = _exact_average(raw.get("average_price")) if isinstance(raw, Mapping) else None
        try:
            if average is None:
                raise ValueError("average price is not a positive Decimal")
            line = position_line_from_kite_row({**raw, "average_price": _PAISE})  # the parser holds paise only
        except ValueError:
            unresolved.append(Unresolved(symbol, "unreadable_row"))
            continue
        if line.product is None:
            unresolved.append(Unresolved(line.contract, "unknown_product"))
            continue
        token = raw.get("instrument_token")
        if token is not None:
            entries = by_token.get(str(token), [])
        else:
            exchange = raw.get("exchange")
            entries = [e for e in catalogue.entries_for_broker_symbol(ZERODHA, line.contract)
                       if not isinstance(exchange, str) or e.broker_refs[ZERODHA].broker_segment.startswith(exchange)]
        contract = entries[0].contract if len(entries) == 1 else None
        kind = None if contract is None else (Instrument.FUT if contract.is_future() else
                                              Instrument(contract.instrument_type) if contract.is_option() else None)
        if contract is None or kind is None or contract.name not in SUPPORTED_UNDERLYINGS or contract.expiry is None:
            unresolved.append(Unresolved(line.contract, "not_in_catalogue"))
            continue
        ref = entries[0].broker_refs[ZERODHA]
        strike = None if kind is Instrument.FUT else contract.strike
        position = SuggestedPosition(entries[0].id, line.contract, contract.name, kind, strike, contract.expiry,
                                     line.net_quantity, average, line.product, ref.lot_size, ref.tick_size)
        if position.key in seen:
            continue
        seen.add(position.key)
        candidates.append((_contract_key(contract.name, kind, strike, contract.expiry), position))

    broker_net: dict[tuple, int] = {}
    for ckey, position in candidates:
        broker_net[ckey] = broker_net.get(ckey, 0) + position.net_quantity

    grouped: dict[str, list[SuggestedPosition]] = {}
    for ckey, position in candidates:
        if ckey in held:
            if broker_net[ckey] == held[ckey]:
                continue  # exactly what a strategy holds: matched by contract identity, never by symbol text
            unresolved.append(Unresolved(position.tradingsymbol, "differs_from_strategy",
                                         f"zerodha={broker_net[ckey]};strategy={held[ckey]}"))
            continue
        if abs(position.net_quantity) % position.lot_size:
            unresolved.append(Unresolved(position.tradingsymbol, "not_lot_multiple"))
            continue
        grouped.setdefault(_group_id(position.underlying, position.expiry), []).append(position)

    label = _make_labeller(catalogue, templates, spots)
    groups = tuple(Group(gid, members[0].underlying, members[0].expiry, tuple(members), label(members))
                   for gid, members in sorted(grouped.items()))
    return GroupSuggestion(groups, tuple(unresolved), label)


def _describe(target: Target | None) -> str:
    if isinstance(target, ToGroup):
        return f"group:{target.group_id}"
    if isinstance(target, ToStrategy):
        return f"strategy:{target.strategy_id}"
    return "standalone" if isinstance(target, Standalone) else "none"


def _ident(key: PositionKey) -> str:
    return f"{key.instrument_id.exchange_segment}:{key.instrument_id.exchange_token}"


class GroupingSession:
    """The user's grouping choices over one suggestion. Every action appends one audit entry (see module docstring)."""

    def __init__(self, suggestion: GroupSuggestion, *, audit: AuditLog, clock: Callable[[], datetime.datetime],
                 actor: str, session_id: str, strategies: Mapping[str, StrategyDefinition] | None = None) -> None:
        self.suggestion = suggestion
        self._audit, self._clock, self._actor, self._session_id = audit, clock, actor, session_id
        self._strategies = dict(strategies or {})
        self._positions = {p.key: p for g in suggestion.groups for p in g.positions}
        self._registry = {g.id: g.underlying for g in suggestion.groups}
        self._place: dict[PositionKey, Target] = {p.key: ToGroup(g.id) for g in suggestion.groups for p in g.positions}
        self._entries: dict[PositionKey, tuple[Decimal, EntrySource]] = {}
        self._adopted_keys: set[PositionKey] = set()
        self._adopted: list[AdoptedStrategy] = []
        self._new_ids: set[str] = set()

    @classmethod
    def start(cls, suggestion: GroupSuggestion, *, audit: AuditLog, clock: Callable[[], datetime.datetime],
              actor: str, session_id: str,
              strategies: Mapping[str, StrategyDefinition] | None = None) -> "GroupingSession":
        """Open the session; appends one ``suggest`` entry listing the suggested groups and the unresolved rows."""
        session = cls(suggestion, audit=audit, clock=clock, actor=actor, session_id=session_id, strategies=strategies)
        session._record(EventType.RECONCILIATION_RECORDED, {
            "action": "suggest",
            "groups": [{"id": g.id, "legs": [f"{p.tradingsymbol}:{p.product.value}" for p in g.positions],
                        "resembles": g.resembles or "none"} for g in suggestion.groups],
            "unresolved": [f"{u.tradingsymbol}:{u.reason}" for u in suggestion.unresolved],
        })
        return session

    # -- views -----------------------------------------------------------------------------------------------------

    @property
    def adopted(self) -> tuple[AdoptedStrategy, ...]:
        return tuple(self._adopted)

    def _live(self, target_type) -> list[SuggestedPosition]:
        return [p for k, p in self._positions.items()
                if k not in self._adopted_keys and isinstance(self._place[k], target_type)]

    def groups(self) -> tuple[Group, ...]:
        """The groups as they now stand (resemblance recomputed); a group with no position left is not listed."""
        out = []
        for gid, underlying in sorted(self._registry.items()):
            members = [p for p in self._live(ToGroup) if self._place[p.key] == ToGroup(gid)]
            if members:
                out.append(Group(gid, underlying, min(p.expiry for p in members), tuple(members),
                                 self.suggestion.labeller(members)))
        return tuple(out)

    def standalone(self) -> tuple[SuggestedPosition, ...]:
        """Positions left standalone: shown, never ordered for, never monitored (ADR-002, ADR-084)."""
        return tuple(self._live(Standalone))

    def entry_of(self, position: SuggestedPosition) -> tuple[Decimal, EntrySource]:
        return self._entries.get(position.key, (position.average_price, EntrySource.FROM_ZERODHA))

    # -- actions ---------------------------------------------------------------------------------------------------

    def _record(self, event_type: EventType, payload: dict) -> None:
        self._audit.append(event_type, actor=self._actor, timestamp=self._clock(), correlation_id=self._session_id,
                           payload=payload)

    def _position(self, key: PositionKey) -> SuggestedPosition:
        position = self._positions.get(key)
        if position is None or key in self._adopted_keys:
            raise ReconciliationError(f"position {key} is not an open suggested position",
                                      message=render("grouping_choice_unavailable"))
        return position

    def move_unresolved(self, tradingsymbol: str, target: Target) -> None:
        """A row in ``unresolved`` cannot be moved anywhere: always refused with its reason's four-part message."""
        for item in self.suggestion.unresolved:
            if item.tradingsymbol == tradingsymbol:
                raise ReconciliationError(f"{item.tradingsymbol}: {item.reason}", message=_unresolved_message(item))
        raise ReconciliationError(f"{tradingsymbol} is not in the open positions",
                                  message=render("grouping_choice_unavailable"))

    def move(self, key: PositionKey, target: Target) -> None:
        position = self._position(key)
        if isinstance(target, ToStrategy):
            raise ReconciliationError(f"adding {position.tradingsymbol} to strategy {target.strategy_id!r}",
                                      message=render("grouping_not_available"))
        if isinstance(target, ToGroup):
            underlying = self._registry.get(target.group_id)
            if underlying is None:
                raise ReconciliationError(f"no group {target.group_id!r}", message=render("grouping_choice_unavailable"))
        elif isinstance(target, Standalone):
            underlying = position.underlying
        else:
            raise ReconciliationError(f"unknown target {target!r}", message=render("grouping_choice_unavailable"))
        if underlying != position.underlying:  # a calendar by explicit move is allowed; another underlying never
            raise ReconciliationError(f"{position.tradingsymbol} is {position.underlying}, target is {underlying}",
                                      message=render("grouping_move_refused"))
        old = self._place[key]
        self._record(EventType.USER_APPROVAL_RECORDED, {
            "action": "standalone" if isinstance(target, Standalone) else "move",
            "position": position.tradingsymbol, "product": key.product.value, "instrument_id": _ident(key),
            "from": _describe(old), "to": _describe(target),
        })
        self._place[key] = target

    def set_entry(self, key: PositionKey, price: object) -> None:
        """The entry the user wants for one leg: a Decimal above zero in paise (not a tick multiple: it is a cost)."""
        position = self._position(key)
        try:
            checked = require_price(price, "entry_price", allow_zero=False)
        except ValueError as exc:
            raise ReconciliationError(f"{position.tradingsymbol}: {exc}",
                                      message=render("grouping_entry_price_invalid")) from exc
        old, _ = self.entry_of(position)
        self._record(EventType.USER_APPROVAL_RECORDED, {
            "action": "set_entry", "position": position.tradingsymbol, "product": key.product.value,
            "instrument_id": _ident(key), "old_price": str(old), "new_price": str(checked),
        })
        self._entries[key] = (checked, EntrySource.EDITED)

    def _fresh_strategy_id(self, strategy_id: str) -> None:
        if not isinstance(strategy_id, str) or not strategy_id.strip() or strategy_id in self._strategies \
                or strategy_id in self._new_ids:
            raise ReconciliationError(f"strategy id {strategy_id!r} is empty or already used",
                                      message=render("grouping_choice_unavailable"))

    def confirm(self, group_id: str, *, strategy_id: str) -> AdoptedStrategy:
        """Create a NEW strategy from the group as it now stands: every row is its own leg with its own entry (Zerodha's
        exact average unless edited) and product. All rows or none: a row whose average needs an entry refuses the
        whole group."""
        group = next((g for g in self.groups() if g.id == group_id), None)
        if group is None:
            raise ReconciliationError(f"no open group {group_id!r} (unknown, empty or adopted)",
                                      message=render("grouping_choice_unavailable"))
        self._fresh_strategy_id(strategy_id)
        needing = [p for p in group.positions if p.needs_entry and p.key not in self._entries]
        if needing:
            raise ReconciliationError(f"{len(needing)} row(s) of {group_id} need an entry price first",
                                      message=render("grouping_entry_needed", contracts=len(needing)))
        legs = []
        for p in group.positions:
            price, source = self.entry_of(p)
            legs.append(AdoptedLeg(p.tradingsymbol, p.instrument_id, p.leg(price), p.product, source))
        adopted = AdoptedStrategy(strategy_id, group.underlying, tuple(legs), group.resembles)
        self._record(EventType.STRATEGY_CHANGED, {
            "action": "confirm", "group": group_id, "strategy_id": strategy_id, "resembles": group.resembles or "none",
            "legs": [{"position": a.tradingsymbol, "entry_price": str(a.leg.entry_price),
                      "entry_source": a.entry_source.value, "product": a.product.value} for a in legs]})
        self._adopted_keys.update(p.key for p in group.positions)
        self._new_ids.add(strategy_id)
        self._adopted.append(adopted)
        return adopted
