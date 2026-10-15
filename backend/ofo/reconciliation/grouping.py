"""Existing Zerodha positions on connect: suggested groups, user moves, adoption, every choice audited.

Spec: REQ-061 AC-1 (identify possible multi-leg structures), AC-2 (add to an existing strategy, create a new
strategy, or leave it standalone), AC-4 (every grouping decision recorded); ADR-084 ("A group is named only as a
resemblance to a template"; "An adopted leg's entry price is Zerodha's average price for that position"); ADR-006 /
ADR-018 (resemblance only, the user confirms); ADR-002 (every order belongs to a strategy: a standalone position is
shown and never gets an order or a monitor).

Domain layer, standard library plus this repo's own parser, matcher, catalogue and audit log. Nothing here places an
order, reads the broker or monitors anything; AC-3 (monitoring the adopted strategy) and the screen are other items.

* ``suggest_groups`` takes Kite position rows (parsed by ``position_line_from_kite_row``), drops rows with a zero
  quantity and rows whose CONTRACT (the exchange identity, resolved through the catalogue by Zerodha's instrument
  token, else by symbol and exchange) is already a leg of a strategy, and groups the rest by (underlying, expiry).
  A group carries the matcher's template name as ``resembles`` or ``None`` (Custom); a strategy is never created.
  Rows that cannot be adopted (not in the catalogue, not a whole number of lots, unreadable) are listed in
  ``unresolved`` with a reason and are in no group.
* ``GroupingSession`` holds the user's choices. Every action appends exactly ONE entry through the audit log's
  public ``append`` (``start`` = the suggestion, ``move`` / ``move to standalone``, ``set_entry``, ``confirm``);
  a refused action changes nothing and appends nothing.
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
from ofo.strategy.matching import Custom, MatchResult, match
from ofo.strategy.model import Template, TemplateError

__all__ = [
    "STANDALONE", "AdoptedLeg", "AdoptedStrategy", "EntrySource", "ExistingStrategyAdoption", "Group",
    "GroupSuggestion", "GroupingError", "GroupingSession", "Standalone", "SuggestedPosition", "ToGroup",
    "ToStrategy", "Unresolved", "suggest_groups",
]


#: A refused grouping choice: ``message`` is the four-part text from ``render()``; ``str()`` is developer detail.
GroupingError = ReconciliationError


class EntrySource(Enum):
    FROM_ZERODHA = "from_zerodha"
    EDITED = "edited"


@dataclass(frozen=True)
class ToGroup:
    group_id: str


@dataclass(frozen=True)
class ToStrategy:
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
    average_price: Decimal
    product: Product | None
    lot_size: int
    tick_size: Decimal

    @property
    def action(self) -> Action:
        return Action.BUY if self.net_quantity > 0 else Action.SELL

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
    """A row that is shown but cannot be adopted. ``reason``: not_in_catalogue | not_lot_multiple | unreadable_row."""

    tradingsymbol: str
    reason: str


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
    product: Product | None
    entry_source: EntrySource


@dataclass(frozen=True)
class AdoptedStrategy:
    """A NEW strategy created by the user's confirm. ``resembles`` is information only."""

    strategy_id: str
    underlying: str
    legs: tuple[AdoptedLeg, ...]
    resembles: str | None


@dataclass(frozen=True)
class ExistingStrategyAdoption:
    """Legs the user confirmed into an EXISTING strategy: a proposal for the strategy-modification flow (W-027); this
    module does not edit a strategy."""

    strategy_id: str
    legs: tuple[AdoptedLeg, ...]


def _group_id(underlying: str, expiry: datetime.date) -> str:
    return f"{underlying}:{expiry.isoformat()}"


def _unresolved_message(item: Unresolved):
    template = "grouping_not_lot_multiple" if item.reason == "not_lot_multiple" else "grouping_unknown_contract"
    return render(template, contracts=1)


def _contract_key(name: str, instrument: Instrument, strike: Decimal | None, expiry: datetime.date) -> tuple:
    return (name, instrument, strike, expiry)


def _held_by_strategies(strategies: Mapping[str, StrategyDefinition]) -> set[tuple]:
    return {_contract_key(d.underlying, leg.instrument, leg.strike, leg.expiry)
            for d in strategies.values() for leg in d.legs}


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
            result = match([p.leg() for p in positions], spot=spot, strike_gap=gap, templates=template_list)
        except (ValueError, TemplateError):  # no strike gap, an off-grid strike, an ambiguous catalogue: no label
            return None
        return result.label if isinstance(result, MatchResult) else None

    return label


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

    grouped: dict[str, list[SuggestedPosition]] = {}
    unresolved: list[Unresolved] = []
    for raw in rows:
        symbol = str(raw.get("tradingsymbol", "?")) if isinstance(raw, Mapping) else "?"
        try:
            line = position_line_from_kite_row(raw)
        except ValueError:
            unresolved.append(Unresolved(symbol, "unreadable_row"))
            continue
        if line.net_quantity == 0:
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
        strike = None if kind is Instrument.FUT else contract.strike
        if _contract_key(contract.name, kind, strike, contract.expiry) in held:
            continue  # already a leg of a strategy: matched by contract identity, never by symbol text
        ref = entries[0].broker_refs[ZERODHA]
        if abs(line.net_quantity) % ref.lot_size:
            unresolved.append(Unresolved(line.contract, "not_lot_multiple"))
            continue
        grouped.setdefault(_group_id(contract.name, contract.expiry), []).append(SuggestedPosition(
            entries[0].id, line.contract, contract.name, kind, strike, contract.expiry, line.net_quantity,
            line.average_price, line.product, ref.lot_size, ref.tick_size))

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


class GroupingSession:
    """The user's grouping choices over one suggestion. Every action appends one audit entry (see module docstring)."""

    def __init__(self, suggestion: GroupSuggestion, *, audit: AuditLog, clock: Callable[[], datetime.datetime],
                 actor: str, session_id: str, strategies: Mapping[str, StrategyDefinition] | None = None) -> None:
        self.suggestion = suggestion
        self._audit, self._clock, self._actor, self._session_id = audit, clock, actor, session_id
        self._strategies = dict(strategies or {})
        self._positions = {p.instrument_id: p for g in suggestion.groups for p in g.positions}
        self._registry = {g.id: g.underlying for g in suggestion.groups}
        self._place: dict[InstrumentId, Target] = {p.instrument_id: ToGroup(g.id)
                                                   for g in suggestion.groups for p in g.positions}
        self._entries: dict[InstrumentId, tuple[Decimal, EntrySource]] = {}
        self._adopted_ids: set[InstrumentId] = set()
        self._adopted: list[AdoptedStrategy | ExistingStrategyAdoption] = []
        self._new_ids: set[str] = set()

    @classmethod
    def start(cls, suggestion: GroupSuggestion, *, audit: AuditLog, clock: Callable[[], datetime.datetime],
              actor: str, session_id: str,
              strategies: Mapping[str, StrategyDefinition] | None = None) -> "GroupingSession":
        """Open the session; appends one ``suggest`` entry listing the suggested groups and the unresolved rows."""
        session = cls(suggestion, audit=audit, clock=clock, actor=actor, session_id=session_id, strategies=strategies)
        session._record(EventType.RECONCILIATION_RECORDED, {
            "action": "suggest",
            "groups": [{"id": g.id, "legs": [p.tradingsymbol for p in g.positions], "resembles": g.resembles or "none"}
                       for g in suggestion.groups],
            "unresolved": [f"{u.tradingsymbol}:{u.reason}" for u in suggestion.unresolved],
        })
        return session

    # -- views -----------------------------------------------------------------------------------------------------

    @property
    def adopted(self) -> tuple[AdoptedStrategy | ExistingStrategyAdoption, ...]:
        return tuple(self._adopted)

    def _live(self, target_type) -> list[SuggestedPosition]:
        return [p for i, p in self._positions.items()
                if i not in self._adopted_ids and isinstance(self._place[i], target_type)]

    def groups(self) -> tuple[Group, ...]:
        """The groups as they now stand (resemblance recomputed); a group with no position left is not listed."""
        out = []
        for gid, underlying in sorted(self._registry.items()):
            members = [p for p in self._live(ToGroup) if self._place[p.instrument_id] == ToGroup(gid)]
            if members:
                out.append(Group(gid, underlying, min(p.expiry for p in members), tuple(members),
                                 self.suggestion.labeller(members)))
        return tuple(out)

    def standalone(self) -> tuple[SuggestedPosition, ...]:
        """Positions left standalone: shown, never ordered for, never monitored (ADR-002, ADR-084)."""
        return tuple(self._live(Standalone))

    def entry_of(self, position: SuggestedPosition) -> tuple[Decimal, EntrySource]:
        return self._entries.get(position.instrument_id, (position.average_price, EntrySource.FROM_ZERODHA))

    # -- actions ---------------------------------------------------------------------------------------------------

    def _record(self, event_type: EventType, payload: dict) -> None:
        self._audit.append(event_type, actor=self._actor, timestamp=self._clock(), correlation_id=self._session_id,
                           payload=payload)

    def _position(self, instrument_id: InstrumentId) -> SuggestedPosition:
        position = self._positions.get(instrument_id)
        if position is None or instrument_id in self._adopted_ids:
            raise ReconciliationError(f"position {instrument_id} is not an open suggested position", message=render("grouping_choice_unavailable"))
        return position

    def move_unresolved(self, tradingsymbol: str, target: Target) -> None:
        """A row in ``unresolved`` cannot be moved anywhere: always refused with its reason's four-part message."""
        for item in self.suggestion.unresolved:
            if item.tradingsymbol == tradingsymbol:
                raise ReconciliationError(f"{item.tradingsymbol}: {item.reason}", message=_unresolved_message(item))
        raise ReconciliationError(f"{tradingsymbol} is not in the open positions", message=render("grouping_choice_unavailable"))

    def move(self, instrument_id: InstrumentId, target: Target) -> None:
        position = self._position(instrument_id)
        if isinstance(target, ToGroup):
            underlying = self._registry.get(target.group_id)
            if underlying is None:
                raise ReconciliationError(f"no group {target.group_id!r}", message=render("grouping_choice_unavailable"))
        elif isinstance(target, ToStrategy):
            definition = self._strategies.get(target.strategy_id)
            if definition is None:
                raise ReconciliationError(f"no strategy {target.strategy_id!r}", message=render("grouping_choice_unavailable"))
            underlying = definition.underlying
        elif isinstance(target, Standalone):
            underlying = position.underlying
        else:
            raise ReconciliationError(f"unknown target {target!r}", message=render("grouping_choice_unavailable"))
        if underlying != position.underlying:  # a calendar by explicit move is allowed; another underlying never
            raise ReconciliationError(f"{position.tradingsymbol} is {position.underlying}, target is {underlying}", message=render("grouping_move_refused"))
        old = self._place[instrument_id]
        self._record(EventType.USER_APPROVAL_RECORDED, {
            "action": "standalone" if isinstance(target, Standalone) else "move",
            "position": position.tradingsymbol, "instrument_id": f"{instrument_id.exchange_segment}:{instrument_id.exchange_token}",
            "from": _describe(old), "to": _describe(target),
        })
        self._place[instrument_id] = target

    def set_entry(self, instrument_id: InstrumentId, price: object) -> None:
        position = self._position(instrument_id)
        try:
            checked = require_price(price, "entry_price", allow_zero=False)
            if checked % position.tick_size:
                raise ValueError(f"{checked} is not a multiple of the tick size {position.tick_size}")
        except ValueError as exc:
            raise ReconciliationError(f"{position.tradingsymbol}: {exc}", message=render("grouping_entry_price_invalid")) from exc
        old, _ = self.entry_of(position)
        self._record(EventType.USER_APPROVAL_RECORDED, {
            "action": "set_entry", "position": position.tradingsymbol,
            "instrument_id": f"{instrument_id.exchange_segment}:{instrument_id.exchange_token}",
            "old_price": str(old), "new_price": str(checked),
        })
        self._entries[instrument_id] = (checked, EntrySource.EDITED)

    def _adopted_legs(self, members: Sequence[SuggestedPosition]) -> tuple[AdoptedLeg, ...]:
        legs = []
        for p in members:
            price, source = self.entry_of(p)
            legs.append(AdoptedLeg(p.tradingsymbol, p.instrument_id, p.leg(price), p.product, source))
        return tuple(legs)

    def _fresh_strategy_id(self, strategy_id: str) -> None:
        if not isinstance(strategy_id, str) or not strategy_id.strip() or strategy_id in self._strategies \
                or strategy_id in self._new_ids:
            raise ReconciliationError(f"strategy id {strategy_id!r} is empty or already used", message=render("grouping_choice_unavailable"))

    def _leg_audit(self, legs: Sequence[AdoptedLeg]) -> list[dict]:
        return [{"position": a.tradingsymbol, "entry_price": str(a.leg.entry_price), "entry_source": a.entry_source.value,
                 "product": a.product.value if a.product else "unknown"} for a in legs]

    def confirm(self, group_id: str, *, strategy_id: str) -> AdoptedStrategy:
        """Create a NEW strategy from the group as it now stands. Entry = Zerodha's average unless edited."""
        group = next((g for g in self.groups() if g.id == group_id), None)
        if group is None:
            raise ReconciliationError(f"no open group {group_id!r} (unknown, empty or adopted)", message=render("grouping_choice_unavailable"))
        self._fresh_strategy_id(strategy_id)
        legs = self._adopted_legs(group.positions)
        adopted = AdoptedStrategy(strategy_id, group.underlying, legs, group.resembles)
        self._record(EventType.STRATEGY_CHANGED, {
            "action": "confirm", "group": group_id, "strategy_id": strategy_id, "legs": self._leg_audit(legs),
            "resembles": group.resembles or "none"})
        self._adopted_ids.update(p.instrument_id for p in group.positions)
        self._new_ids.add(strategy_id)
        self._adopted.append(adopted)
        return adopted

    def confirm_existing(self, strategy_id: str) -> ExistingStrategyAdoption:
        """Confirm the positions moved into an existing strategy: a proposal for the modification flow (W-027)."""
        members = [p for p in self._live(ToStrategy) if self._place[p.instrument_id] == ToStrategy(strategy_id)]
        if not members:
            raise ReconciliationError(f"no position was moved into strategy {strategy_id!r}", message=render("grouping_choice_unavailable"))
        legs = self._adopted_legs(members)
        proposal = ExistingStrategyAdoption(strategy_id, legs)
        self._record(EventType.STRATEGY_CHANGED, {
            "action": "confirm_existing", "strategy_id": strategy_id, "legs": self._leg_audit(legs)})
        self._adopted_ids.update(p.instrument_id for p in members)
        self._adopted.append(proposal)
        return proposal
